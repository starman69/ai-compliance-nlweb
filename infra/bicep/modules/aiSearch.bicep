// Azure AI Search for the `azure` profile: hosts compliance-docs-index +
// compliance-chunks-index (1536-d vector + semantic ranker). Index schemas are
// applied from scripts/aisearch/*.json after deploy (see deploy.sh / bootstrap).
@description('Azure AI Search service name. 2-60 chars, lowercase alphanumeric + hyphens.')
param name string
param location string
param tags object

@minValue(1)
@maxValue(12)
param replicaCount int = 1

@allowed([1, 2, 3, 4, 6, 12])
param partitionCount int = 1

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: name
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  sku: { name: 'basic' }
  properties: {
    replicaCount: replicaCount
    partitionCount: partitionCount
    publicNetworkAccess: 'enabled' // POC
    semanticSearch: 'free'         // semantic ranker (the azure-profile reranker)
    authOptions: { aadOrApiKey: { aadAuthFailureMode: 'http403' } }
    disableLocalAuth: false        // POC: keep keys; production = true (MI only)
    hostingMode: 'default'
  }
}

output name string = search.name
output id string = search.id
output endpoint string = 'https://${search.name}.search.windows.net'
