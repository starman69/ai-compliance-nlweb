// Azure AI Document Intelligence (Form Recognizer) for the `azure` runtime
// profile's layout/PDF extraction (prebuilt-layout model) — the cloud analogue
// of the local `unstructured.io` service. Accessed by the api's managed identity
// (no keys), so layout extraction at ingest runs MI-only like the rest of azure.
@description('Document Intelligence account name.')
param name string
param location string
param tags object

resource docintel 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  tags: tags
  kind: 'FormRecognizer' // Azure AI Document Intelligence
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: name
    publicNetworkAccess: 'Enabled' // POC
    disableLocalAuth: true         // Managed Identity only — no keys
    networkAcls: { defaultAction: 'Allow' }
  }
}

output endpoint string = docintel.properties.endpoint
output name string = docintel.name
