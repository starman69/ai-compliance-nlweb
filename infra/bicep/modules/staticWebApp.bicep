// Static Web App hosting the React NLWeb client (azure profile). The build is
// configured (at CI/deploy time) to call the api container app's FQDN for
// /ask, /mcp, /corpus.
param name string
param location string
param tags object

resource swa 'Microsoft.Web/staticSites@2023-12-01' = {
  name: name
  location: location
  tags: tags
  sku: { name: 'Free', tier: 'Free' }
  properties: {
    allowConfigFileUpdates: true
  }
}

output name string = swa.name
output defaultHostname string = swa.properties.defaultHostname
