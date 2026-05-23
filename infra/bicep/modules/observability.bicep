// Log Analytics (required by the Container Apps environment) + Application Insights.
param name string
param location string
param tags object

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${name}-logs'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${name}-ai'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

output logAnalyticsId string = logs.id
output customerId string = logs.properties.customerId
#disable-next-line outputs-should-not-contain-secrets
output sharedKey string = logs.listKeys().primarySharedKey
output appInsightsConnectionString string = appInsights.properties.ConnectionString
