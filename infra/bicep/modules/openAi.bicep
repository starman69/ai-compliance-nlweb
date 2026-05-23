// Azure OpenAI for the `azure` runtime profile: gpt-4.1 (answers) +
// text-embedding-3-small (1536-d embeddings -> Azure AI Search).
@description('Azure OpenAI account name.')
param name string
param location string
param tags object

@description('Per-deployment capacity in 1000-token units (TPM/1000).')
param capacity object = {
  gpt41: 30
  embedding: 50
}

resource account 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: name
    publicNetworkAccess: 'Enabled' // POC
    disableLocalAuth: true         // Managed Identity only
    networkAcls: { defaultAction: 'Allow' }
  }
}

// Answer model — keep in sync with shared.clients.answer_model() azure default.
resource gpt41 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: account
  name: 'gpt-4.1'
  sku: { name: 'GlobalStandard', capacity: capacity.gpt41 }
  properties: {
    model: { format: 'OpenAI', name: 'gpt-4.1', version: '2025-04-14' }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
    raiPolicyName: 'Microsoft.DefaultV2'
  }
}

// Embedding model — 1536-d; must match the AI Search index dimensions
// (scripts/aisearch/compliance-*-index.json) and shared.clients.embed_model().
resource embedding 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: account
  name: 'text-embedding-3-small'
  dependsOn: [gpt41]
  sku: { name: 'Standard', capacity: capacity.embedding }
  properties: {
    model: { format: 'OpenAI', name: 'text-embedding-3-small', version: '1' }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
    raiPolicyName: 'Microsoft.DefaultV2'
  }
}

output name string = account.name
output id string = account.id
output endpoint string = account.properties.endpoint
