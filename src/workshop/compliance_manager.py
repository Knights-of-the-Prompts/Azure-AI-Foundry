"""
Compliance Manager interactive agent for Bayer security & compliance officers.

This module provides a minimal interactive CLI and a programmatic `ComplianceManager`
class that delegates queries to the deep research agent (via create_deep_research_agent.answer_query)
and enforces a strict "no hallucination" policy: if the deep research agent returns no
URL citations, the Compliance Manager will refuse to provide an authoritative factual
answer and will request clarification or suggest official sources instead.

Usage (CLI):
    python -m src.workshop.compliance_manager

Programmatic usage:
    from src.workshop.compliance_manager import ComplianceManager
    cm = ComplianceManager()
    resp = cm.handle_query("What are the FDA requirements for electronic records?")

The response is a dict: {"status","message_text","citations","note"}
"""

from typing import Dict, Any, List
import sys
import textwrap
import json
import os
import re
from urllib.parse import urlparse

# Import `answer_query` from the sibling module in a robust way so the script can be
# executed as a package (python -m ...) or directly (python src/workshop/compliance_manager.py).
try:
    from .create_deep_research_agent import answer_query  # package import
except Exception:
    try:
        from src.workshop.create_deep_research_agent import answer_query  # absolute package import
    except Exception:
        try:
            # Try simple local import if module is on sys.path
            import create_deep_research_agent as _cdr
            answer_query = _cdr.answer_query
        except Exception:
            # Fallback: load module from file next to this script
            import importlib.util
            import os
            module_path = os.path.join(os.path.dirname(__file__), "create_deep_research_agent.py")
            spec = importlib.util.spec_from_file_location("create_deep_research_agent", module_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            answer_query = mod.answer_query


class ComplianceManager:
    def __init__(self, require_citations: bool = True, authoritative_domains: List[str] = None):
        """require_citations: if True, only return answers that include at least one URL citation.

        authoritative_domains: optional list of additional authoritative domain names to accept.
        """
        self.require_citations = require_citations
        # Default whitelist of authoritative domains (common regulatory and DPA sites)
        self.authoritative_domains = {
            "fda.gov",
            "ecfr.gov",
            "gov.uk",
            "ema.europa.eu",
            "who.int",
            "eur-lex.europa.eu",
            "edpb.europa.eu",
            "curia.europa.eu",
            "ec.europa.eu",
            "commission.europa.eu",
            "cnil.fr",
            "ico.org.uk",
        }
        if authoritative_domains:
            for d in authoritative_domains:
                self.authoritative_domains.add(d)

    def handle_query(self, query: str) -> Dict[str, Any]:
        """Send the query to the deep research agent and format the response.

        If require_citations is True and the result contains no citations, return a
        refusal-style response explaining that no authoritative sources were found.
        """
        result = answer_query(query)

        response: Dict[str, Any] = {
            "status": result.get("status"),
            "message_text": "",
            "citations": result.get("citations", []),
            "note": None,
        }

        # If the run failed or timed out, pass through error
        if result.get("error"):
            response["note"] = f"Error from research agent: {result.get('error')}"
            return response

        # If empty answer
        msg = (result.get("message_text") or "").strip()
        if not msg:
            response["note"] = "No substantive answer was returned by the research agent."
            return response

        # If the deep research agent didn't return structured citations, attempt to extract inline URLs from the text
        citations = response["citations"]
        if not citations:
            extracted = self._extract_urls_from_text(msg)
            # Filter extracted URLs by authoritative domains
            filtered = [u for u in extracted if self._is_authoritative(u)]
            response["citations"] = [{"title": u, "url": u} for u in filtered]
            citations = response["citations"]

        # If citations are required but none were found even after extraction, refuse to answer authoritatively
        if self.require_citations and not citations:
            response["note"] = (
                "I could not find authoritative, citable sources for this query. "
                "To avoid hallucination, I won't provide a definitive answer. "
                "Please refine your question or provide additional context (scope, jurisdiction, timeframe)."
            )
            # Still include the raw text as non-authoritative content for user review
            response["message_text"] = textwrap.shorten(msg, width=1000)
            return response

        # Otherwise, return the answer along with citations
        response["message_text"] = msg
        return response

    def _extract_urls_from_text(self, text: str) -> List[str]:
        """Extract http/https URLs from text."""
        if not text:
            return []
        # Improved regex: capture until whitespace or common delimiters
        url_pattern = r"https?://[^\s'\"<>()]+"
        found = re.findall(url_pattern, text)
        # normalize by strip surrounding brackets/whitespace and trailing punctuation
        cleaned = [u.strip("[]()<>\n\r\t").rstrip('.,;:') for u in found]
        return cleaned

    def _is_authoritative(self, url: str) -> bool:
        try:
            hostname = urlparse(url).hostname or ""
            # check if any authoritative domain is a suffix of the hostname
            for d in self.authoritative_domains:
                if hostname == d or hostname.endswith('.' + d):
                    return True
            return False
        except Exception:
            return False

    def _dedupe_citations(self, citations: List[dict]) -> List[dict]:
        """Deduplicate citation list by URL, preserving order."""
        seen = set()
        out = []
        for c in citations:
            url = c.get("url") if isinstance(c, dict) else c
            if not url:
                continue
            if url in seen:
                continue
            seen.add(url)
            if isinstance(c, dict):
                out.append(c)
            else:
                out.append({"title": url, "url": url})
        return out

    def _extract_json_from_text(self, text: str):
        """Attempt to locate and parse the first JSON object in the text.

        Handles fenced code blocks (```json ... ``` or ``` ... ```), and plain JSON.
        Returns parsed JSON (dict/list) or None.
        """
        if not text:
            return None

        # First look for fenced code block ```json ... ``` or ``` ... ```
        m = re.search(r"```\s*(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
        candidate_texts = []
        if m:
            candidate_texts.append(m.group(1).strip())

        # Always try to find the first balanced JSON object in the full text as a fallback
        def find_balanced_json(s: str):
            start = s.find('{')
            if start == -1:
                return None
            i = start
            depth = 0
            in_string = False
            escape = False
            while i < len(s):
                ch = s[i]
                if in_string:
                    if escape:
                        escape = False
                    elif ch == '\\':
                        escape = True
                    elif ch == '"':
                        in_string = False
                else:
                    if ch == '"':
                        in_string = True
                    elif ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            return s[start:i+1]
                i += 1
            return None

        # Add the balanced JSON candidate
        fallback = find_balanced_json(text)
        if fallback:
            candidate_texts.append(fallback)

        for cand in candidate_texts:
            try:
                return json.loads(cand)
            except Exception:
                # try to clean up common issues (e.g., trailing commas)
                try:
                    cleaned = re.sub(r",\s*}\s*", "}", cand)
                    return json.loads(cleaned)
                except Exception:
                    continue

        return None

    def search_updates(self, topic: str, jurisdiction: str = None) -> Dict[str, Any]:
        """Search for the latest updates regarding rules and regulations for a topic.

        Returns structured result from the deep research agent. Enforces citation requirement
        when `require_citations` is True.
        """
        q = f"Latest official updates on rules and regulations regarding {topic}."
        if jurisdiction:
            q += f" Focus on {jurisdiction}."

        result = answer_query(q)

        resp = {
            "status": result.get("status"),
            "message_text": result.get("message_text", "").strip(),
            "citations": result.get("citations", []),
            "note": None,
        }

        if result.get("error"):
            resp["note"] = f"Error from research agent: {result.get('error')}"
            return resp

        # If structured citations are missing, attempt to extract inline URLs from the returned text
        if not resp["citations"]:
            extracted = self._extract_urls_from_text(resp["message_text"])
            filtered = [u for u in extracted if self._is_authoritative(u)]
            resp["citations"] = [{"title": u, "url": u} for u in filtered]

        if self.require_citations and not resp["citations"]:
            resp["note"] = (
                "No authoritative citations were found for the requested topic. "
                "Please refine the topic, specify jurisdiction, or allow non-cited responses."
            )

        return resp

    # Category-driven helpers
    CATEGORY_MAP = {
        "Data protection & Privacy": {
            "scope": "GDPR",
            "description": "Scope: GDPR (data protection and privacy in the EU).",
            "default_controls": (
                "Control ID: DP-01\nControl Name: Data inventory and mapping\nDescription: Maintain a data inventory and perform data mapping for all personal data processing activities.\n\n"
                "Control ID: DP-02\nControl Name: Data minimization and retention\nDescription: Apply data minimization and retention limits aligned with GDPR principles.\n\n"
                "Control ID: DP-03\nControl Name: Access controls and encryption\nDescription: Limit access to personal data and apply encryption at rest and in transit.\n"
            ),
        },
        "Pharamaceutical regulations": {
            "scope": "EMA, FDA, ICH guidelines, GMP guidelines, 21 CFR Part 11",
            "description": "Scope: EMA, FDA, ICH, GMP and 21 CFR Part 11 for pharmaceutical compliance.",
            "default_controls": (
                "Control ID: P-01\nControl Name: System validation\nDescription: Validate computerized systems used in manufacturing and clinical trials.\n\n"
                "Control ID: P-02\nControl Name: Data integrity and ALCOA+\nDescription: Ensure data are attributable, legible, contemporaneous, original, accurate and plus (complete, consistent, enduring, available).\n\n"
                "Control ID: P-03\nControl Name: Supply chain traceability\nDescription: Implement DSCSA/EU serialization and track-and-trace mechanisms where applicable.\n"
            ),
        },
        "ISO standards": {
            "scope": "ISO 9001, ISO 14001, ISO 13485, ISO 17025",
            "description": "Scope: Key ISO standards for quality, environment, medical devices, and labs.",
            "default_controls": (
                "Control ID: I-01\nControl Name: Quality management system\nDescription: Maintain documented QMS aligning to ISO 9001 requirements.\n\n"
                "Control ID: I-02\nControl Name: Environmental management\nDescription: Environmental objectives, monitoring and compliance processes per ISO 14001.\n\n"
                "Control ID: I-03\nControl Name: Device quality controls\nDescription: Processes aligning to ISO 13485 for medical devices.\n"
            ),
        },
        "Environmental & Sustainability regulations": {
            "scope": "REACH, EU chemical safety, global environmental laws",
            "description": "Scope: REACH, EU chemical safety, and global environmental and sustainability laws; includes waste management and emissions control.",
            "default_controls": (
                "Control ID: E-01\nControl Name: Chemical inventory and REACH compliance\nDescription: Maintain chemical inventories and ensure REACH registration/authorization where applicable.\n\n"
                "Control ID: E-02\nControl Name: Emissions and waste controls\nDescription: Monitor emissions and waste streams and maintain compliance with national limits and permits.\n\n"
                "Control ID: E-03\nControl Name: Environmental management & reporting\nDescription: Track sustainability KPIs and report per regulatory and company frameworks.\n"
            ),
        },
    }

    def create_compliance_report(self, scope: str, controls_text: str, jurisdiction: str = None,
                                 require_structured_json: bool = True) -> Dict[str, Any]:
        """Create a compliance report for the given scope and controls.

        The method will:
        - Fetch applicable regulations and authoritative guidance for the scope/jurisdiction.
        - Ask the deep research agent to evaluate the provided controls against the regulations,
          identify and flag potential violations, and evaluate control effectiveness.
        - Prefer structured JSON output when require_structured_json=True. If the research agent
          returns no citations, the method will decline to produce an authoritative report.

        Returns a dict with fields: status, scope, jurisdiction, regulations, evaluation, report_json (if parsed), note
        """
        # 1) Fetch regulations/guidance
        reg_query = f"Authoritative regulations, laws, and official guidance for {scope}."
        if jurisdiction:
            reg_query += f" Focus on {jurisdiction}."
        reg_query += " Provide a concise summary and include URL citations for each regulation."

        regs = answer_query(reg_query)

        report = {
            "status": regs.get("status"),
            "scope": scope,
            "jurisdiction": jurisdiction,
            "regulations_summary": regs.get("message_text", "").strip(),
            "regulations_citations": regs.get("citations", []),
            "evaluation_text": "",
            "evaluation_citations": [],
            "report_json": None,
            "note": None,
        }

        if regs.get("error"):
            report["note"] = f"Error fetching regulations: {regs.get('error')}"
            return report

        # If regulations_citations are empty, attempt to extract inline URLs from the summary
        if not report["regulations_citations"]:
            extracted = self._extract_urls_from_text(report["regulations_summary"])
            filtered = [u for u in extracted if self._is_authoritative(u)]
            if filtered:
                # populate regulations_citations from filtered inline URLs
                report["regulations_citations"] = [{"title": u, "url": u} for u in filtered]

        # If still lacking citations and require_citations is True, refuse
        if self.require_citations and not report["regulations_citations"]:
            report["note"] = (
                "Unable to locate authoritative citations for the applicable regulations. "
                "To avoid hallucination, cannot produce a definitive compliance report."
            )
            return report

        # 2) Ask deep research agent to evaluate the controls against the regulations
        # Request structured JSON output with specific fields and require citations for findings.
        eval_prompt = (
            "You are an expert compliance analyst. Based on the regulations cited below, "
            "evaluate the following controls and identify any violations, gaps, and an effectiveness rating for each control. "
            "Return a JSON object with keys: flagged_violations (list), control_effectiveness (list of {control_id, rating, rationale, citations}), "
            "recommendations (list). For every factual claim include URL citations.\n\n"
        )
        # Include short versions of the regulations and controls to keep the prompt concise
        eval_prompt += "Regulations summary:\n" + report["regulations_summary"][:4000] + "\n\n"
        eval_prompt += "Controls to evaluate:\n" + controls_text[:4000] + "\n\n"
        eval_prompt += "Return only valid JSON."

        # Increase timeout for the evaluation run since it may take longer
        evaluation = answer_query(eval_prompt, timeout_seconds=600)

        report["evaluation_text"] = evaluation.get("message_text", "").strip()
        report["evaluation_citations"] = evaluation.get("citations", [])

        if evaluation.get("error"):
            report["note"] = f"Error during controls evaluation: {evaluation.get('error')}"
            return report

        if self.require_citations and not report["evaluation_citations"]:
            report["note"] = (
                "Controls evaluation returned no authoritative citations. "
                "To avoid hallucination, the report is informational only."
            )

        # Try to parse JSON result if requested, using the robust extractor and fallbacks
        if require_structured_json:
            txt = report["evaluation_text"]
            parsed = None
            parse_error = None
            if txt:
                try:
                    parsed = self._extract_json_from_text(txt)
                except Exception as ex:
                    parse_error = str(ex)

            # Fallback: try to parse any fenced blocks as JSON
            if parsed is None and txt:
                try:
                    fenced = re.findall(r"```(?:json)?\s*(.*?)```", txt, flags=re.DOTALL | re.IGNORECASE)
                    for block in fenced:
                        try:
                            parsed = json.loads(block.strip())
                            break
                        except Exception:
                            continue
                except Exception:
                    pass

            if parsed is not None:
                report["report_json"] = parsed

                # Collect evaluation citations from multiple sources:
                eval_citations = []
                # 1) Structured citations returned by the evaluation run
                raw_eval_cits = evaluation.get("citations", []) or []
                for c in raw_eval_cits:
                    if isinstance(c, dict) and c.get("url"):
                        eval_citations.append({"title": c.get("title") or c.get("url"), "url": c.get("url")})
                    elif isinstance(c, str) and c.startswith("http"):
                        eval_citations.append({"title": c, "url": c})

                # 2) Any URLs found in the evaluation text
                for u in self._extract_urls_from_text(txt):
                    eval_citations.append({"title": u, "url": u})

                # 3) URLs present inside the parsed JSON (e.g., control effectiveness citations)
                def collect_urls_from_obj(obj):
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if k and k.lower() in ("citations", "urls", "references") and isinstance(v, list):
                                for item in v:
                                    if isinstance(item, str) and item.startswith("http"):
                                        eval_citations.append({"title": item, "url": item})
                            else:
                                collect_urls_from_obj(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            collect_urls_from_obj(item)
                    elif isinstance(obj, str):
                        if obj.startswith("http"):
                            eval_citations.append({"title": obj, "url": obj})

                collect_urls_from_obj(parsed)

                # Deduplicate and keep only authoritative domains
                eval_citations = self._dedupe_citations(eval_citations)
                filtered = [c for c in eval_citations if self._is_authoritative(c.get("url"))]
                report["evaluation_citations"] = filtered

                if self.require_citations and not report.get("evaluation_citations"):
                    report["note"] = (report.get("note") or "") + " Controls evaluation returned no authoritative citations after parsing."
            else:
                report["note"] = (report.get("note") or "") + (f" Failed to parse JSON: {parse_error or 'no JSON found.'}")

        return report


def _interactive_cli():
    cm = ComplianceManager(require_citations=True)

    banner = "Compliance Manager - Bayer (interactive). Type 'exit' to quit."
    print(banner)
    print("This tool only returns answers backed by official sources. If none are found, it will ask you to refine the query.")

    try:
        while True:
            print("\nPlease choose a category (enter the number):")
            categories = list(cm.CATEGORY_MAP.keys())
            for i, cat in enumerate(categories, start=1):
                print(f"  {i}. {cat}")
            print("  0. Exit")

            choice = input("Selection: ").strip()
            if choice in ("0", "exit", "quit"):
                print("Goodbye.")
                break
            try:
                idx = int(choice) - 1
                if idx < 0 or idx >= len(categories):
                    print("Invalid selection, try again.")
                    continue
            except ValueError:
                print("Please enter a number corresponding to a category.")
                continue

            category = categories[idx]
            meta = cm.CATEGORY_MAP[category]
            print(f"\nSelected: {category}\n{meta['description']}")

            # 1) Summarize latest updates
            print("\nFetching latest updates (this may take a minute)...")
            updates = cm.search_updates(meta['scope'])
            print("\n--- Latest updates ---")
            if updates.get('note'):
                print("NOTE:", updates.get('note'))
            if updates.get('message_text'):
                print(textwrap.fill(updates.get('message_text'), width=100))
            if updates.get('citations'):
                print('\nCitations:')
                for c in updates.get('citations'):
                    print(f"- {c.get('url')}")

            # Enter a refine-confirm loop: if the agent requested refinement (in note or message_text),
            # let the user provide refinements repeatedly until the agent returns a substantive answer
            # and the user confirms that the answer is sufficient. Only then offer to create the report.
            refinement_phrases = ['refine', 'could not find', 'could not locate', 'no authoritative', 'please refine', 'unable to locate', 'need more', 'clarify', 'specify jurisdiction', 'provide additional']
            def needs_refinement_check(obj: Dict[str, Any]) -> bool:
                note = (obj.get('note') or '').lower()
                msg = (obj.get('message_text') or '').lower()
                for p in refinement_phrases:
                    if p in note or p in msg:
                        return True
                return False

            # If initial updates indicate refinement is needed, enter loop
            refined_result = updates
            while needs_refinement_check(refined_result):
                print('\nThe agent requested more context before producing authoritative results.')
                refine = input('Provide additional context/jurisdiction/timeframe (or press Enter to cancel): ').strip()
                if not refine:
                    print('No refinement provided — returning to main menu.')
                    refined_result = None
                    break

                print('\nRe-running the agent with your refinement (this may take a minute)...')
                refined_query = f"Latest official updates on {meta['scope']}. {refine}"
                refined_result = cm.handle_query(refined_query)

                if refined_result is None:
                    print('Error: no response from agent. Returning to main menu.')
                    break

                if refined_result.get('note'):
                    print('NOTE:', refined_result.get('note'))
                if refined_result.get('message_text'):
                    print(textwrap.fill(refined_result.get('message_text'), width=100))
                if refined_result.get('citations'):
                    print('\nCitations:')
                    for c in refined_result.get('citations'):
                        print(f"- {c.get('url')}")

                # Ask the user whether the refined result is sufficient
                confirm = input('\nIs this information sufficient to proceed with a compliance report? (y/N): ').strip().lower()
                if confirm == 'y':
                    break
                else:
                    # Loop again to allow additional refinement
                    continue

            # If user cancelled refinement, go back to the main menu
            if refined_result is None:
                continue

            # At this point we have either the original updates (if no refinement was needed) or
            # a refined_result that the user confirmed as sufficient. Per configuration, do not
            # prompt to create a compliance report here. Return to the main menu so the user can
            # explicitly request report generation when ready.
            print('\nRefined results confirmed. If you want to create a compliance report, use the programmatic API or the dedicated report command (not available in this interactive flow). Returning to main menu.')
            continue

    except KeyboardInterrupt:
        print("\nInterrupted. Exiting.")
        sys.exit(0)


if __name__ == "__main__":
    _interactive_cli()
