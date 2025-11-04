// Execute this main file to depoy Azure AI Foundry resources in the basic security configuraiton

// Parameters
@minLength(2)
@maxLength(12)
@description('Name for the AI resource and used to derive name of dependent resources.')
param aiFoundryName string = 'aiagents'

@description('Friendly name for your Azure AI Foundry resource')
param aiFoundryFriendlyName string = 'Agent Workshop AI Foundry resource'

@description('Description of your Azure AI Foundry resource displayed in AI Foundry')
param aiFoundryDescription string = 'This is an example AI Foundry resource for use in Azure AI Foundry.'

@description('Azure region used for the deployment of all resources.')
param location string = resourceGroup().location

@description('Set of tags to apply to all resources.')
param tags object = {}

@description('Project description')
param aiProjectDescription string = 'Agent Workshop'

@description('Budget amount in USD for the resource group')
param budgetAmount int = 500

@description('Email addresses to receive budget alerts (optional)')
param budgetAlertEmails array = ['douwe.vande.ruit@capgemini.com']

@description('Whether to deploy the budget alert (requires subscription-level permissions)')
param deployBudgetAlert bool = false

// Variables
var name = toLower('${aiFoundryName}')

// Create a short, unique suffix, that will be unique to each resource group
var uniqueSuffix = substring(uniqueString(resourceGroup().id), 0, 4)

// Dependent resources for the Azure AI Foundry workspace
module aiDependencies 'modules/dependent-resources.bicep' = {
  name: 'dependencies-${name}-${uniqueSuffix}-deployment'
  params: {
    location: location
    storageName: 'st${name}${uniqueSuffix}'
    keyvaultName: 'kv-${name}-${uniqueSuffix}'
    applicationInsightsName: 'appi-${name}-${uniqueSuffix}'
    containerRegistryName: 'cr${name}${uniqueSuffix}'
    tags: tags
  }
}

module aiFoundry 'modules/ai-foundry.bicep' = {
  name: 'foundry-${name}-${uniqueSuffix}-deployment'
  params: {
    // workspace organization
    aiFoundryName: 'aif-${name}-${uniqueSuffix}'
    aiFoundryFriendlyName: aiFoundryFriendlyName
    aiFoundryDescription: aiFoundryDescription
    location: location
    tags: tags
    customSubDomainName: 'aif-${name}-${uniqueSuffix}'
  }
}

module aiProject 'modules/ai-project.bicep' = {
  name: 'project-${name}-${uniqueSuffix}-deployment'
  params: {
    location: location
    tags: tags
    aiProjectName: 'prj-${name}-${uniqueSuffix}'
    aiProjectDescription: aiProjectDescription
    aiFoundryId: aiFoundry.outputs.aiFoundryId
  }
}

module gpt4oDeployment 'modules/aoai-model-deployment.bicep' = {
  name: 'gpt4o-${name}-${uniqueSuffix}-deployment'
  params: {
    openAIAccountId: aiFoundry.outputs.aiFoundryId
    deploymentName: 'gpt4o'
    modelName: 'gpt-4o'
    capacity: 30
  }
  dependsOn: [
    aiProject
  ]
}

module o3DeepResearchDeployment 'modules/aoai-model-deployment.bicep' = {
  name: 'o3-deep-research-${name}-${uniqueSuffix}-deployment'
  params: {
    openAIAccountId: aiFoundry.outputs.aiFoundryId
    deploymentName: 'o3-deep-research'
    modelName: 'o3-deep-research'
    modelVersion: '2025-06-26'
    capacity: 250
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
    raiPolicyName: 'Microsoft.DefaultV2'
  }
  dependsOn: [
    gpt4oDeployment
  ]
}

module budgetAlert 'modules/budget-alert.bicep' = if (deployBudgetAlert) {
  name: 'budget-${name}-${uniqueSuffix}-deployment'
  params: {
    budgetName: 'budget-${name}-${uniqueSuffix}'
    budgetAmount: budgetAmount
    alertEmails: budgetAlertEmails
  }
}
