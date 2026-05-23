// Grant the api container app's managed identity access to Azure OpenAI + AI Search
// (MI-only auth; no keys in app settings).
param openAiName string
param searchName string
param docIntelName string
param principalId string

resource openAi 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = { name: openAiName }
resource search 'Microsoft.Search/searchServices@2023-11-01' existing = { name: searchName }
resource docIntel 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = { name: docIntelName }

var cognitiveServicesOpenAiUser = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var cognitiveServicesUser = 'a97b65f3-24c7-4388-baec-2e87135dc908'
var searchIndexDataContributor = '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
var searchServiceContributor = '7ca78c08-252a-4471-8644-bb5ff32d4ba0'

resource openAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openAi.id, principalId, cognitiveServicesOpenAiUser)
  scope: openAi
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesOpenAiUser)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource searchData 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, principalId, searchIndexDataContributor)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataContributor)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource searchMgmt 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, principalId, searchServiceContributor)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchServiceContributor)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// Document Intelligence — Cognitive Services User lets the api MI call the
// prebuilt-layout model for PDF/layout extraction at ingest time.
resource docIntelUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(docIntel.id, principalId, cognitiveServicesUser)
  scope: docIntel
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUser)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}
