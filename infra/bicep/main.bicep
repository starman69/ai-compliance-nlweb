// AI Compliance NLWeb — Azure infrastructure for the `azure` runtime profile.
// Deploy: see deploy.sh (resource-group scoped). Pairs with the `local` Docker
// stack in infra/compose/ — same app, two runtimes (ADR 0001).
targetScope = 'resourceGroup'

@description('Short prefix for resource names (lowercase alphanumeric).')
param namePrefix string = 'compliance'

@description('Region. Use one with gpt-4.1 + text-embedding-3-small capacity (e.g. eastus2).')
param location string = resourceGroup().location

@description('Container image for the api (FastAPI), e.g. <acr>.azurecr.io/compliance-api:latest')
param apiImage string

param tags object = { app: 'ai-compliance-nlweb', profile: 'azure' }

var suffix = uniqueString(resourceGroup().id)

module obs 'modules/observability.bicep' = {
  name: 'observability'
  params: { name: '${namePrefix}-${suffix}', location: location, tags: tags }
}

module openAi 'modules/openAi.bicep' = {
  name: 'openAi'
  params: { name: '${namePrefix}-oai-${suffix}', location: location, tags: tags }
}

module search 'modules/aiSearch.bicep' = {
  name: 'aiSearch'
  params: { name: '${namePrefix}-search-${suffix}', location: location, tags: tags }
}

module docintel 'modules/documentIntelligence.bicep' = {
  name: 'documentIntelligence'
  params: { name: '${namePrefix}-docintel-${suffix}', location: location, tags: tags }
}

module web 'modules/staticWebApp.bicep' = {
  name: 'staticWebApp'
  params: { name: '${namePrefix}-web-${suffix}', location: location, tags: tags }
}

module apps 'modules/containerApps.bicep' = {
  name: 'containerApps'
  params: {
    name: namePrefix
    location: location
    tags: tags
    apiImage: apiImage
    logAnalyticsCustomerId: obs.outputs.customerId
    logAnalyticsSharedKey: obs.outputs.sharedKey
    openAiEndpoint: openAi.outputs.endpoint
    searchEndpoint: search.outputs.endpoint
    docIntelEndpoint: docintel.outputs.endpoint
    appInsightsConnectionString: obs.outputs.appInsightsConnectionString
    corsAllowOrigins: 'https://${web.outputs.defaultHostname}'
  }
}

module rbac 'modules/roleAssignments.bicep' = {
  name: 'roleAssignments'
  params: {
    openAiName: openAi.outputs.name
    searchName: search.outputs.name
    docIntelName: docintel.outputs.name
    principalId: apps.outputs.apiPrincipalId
  }
}

output apiFqdn string = apps.outputs.apiFqdn
output webUrl string = 'https://${web.outputs.defaultHostname}'
output openAiEndpoint string = openAi.outputs.endpoint
output searchEndpoint string = search.outputs.endpoint
