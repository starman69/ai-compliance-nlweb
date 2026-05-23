// Container Apps environment + the FastAPI `api` app for the `azure` profile.
// The app settings below are the azure-profile contract — they must stay in sync
// with shared.clients (deployment/index names) and the AI Search index JSONs
// (tests/unit/test_bicep_app_contract.py enforces this).
param name string
param location string
param tags object

@description('Container image for the api (FastAPI), e.g. <acr>.azurecr.io/compliance-api:latest')
param apiImage string

param logAnalyticsCustomerId string
@secure()
param logAnalyticsSharedKey string

param openAiEndpoint string
param searchEndpoint string
param docIntelEndpoint string
param appInsightsConnectionString string
param corsAllowOrigins string

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${name}-env'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
  }
}

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${name}-api'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: { external: true, targetPort: 8000, transport: 'auto' }
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImage
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: [
            { name: 'RUNTIME_PROFILE', value: 'azure' }
            { name: 'NLWEB_BACKEND', value: 'real' }
            { name: 'OPENAI_ENDPOINT', value: openAiEndpoint }
            { name: 'OPENAI_API_VERSION', value: '2024-10-21' }
            { name: 'OPENAI_DEPLOYMENT_REASONING', value: 'gpt-4.1' }
            { name: 'OPENAI_DEPLOYMENT_EMBEDDING', value: 'text-embedding-3-small' }
            { name: 'SEARCH_SERVICE_ENDPOINT', value: searchEndpoint }
            { name: 'DOCINTEL_ENDPOINT', value: docIntelEndpoint }
            { name: 'SEARCH_INDEX_DOCS', value: 'compliance-docs-index' }
            { name: 'SEARCH_INDEX_CHUNKS', value: 'compliance-chunks-index' }
            { name: 'RERANKER_ENABLED', value: 'false' } // azure uses the AI Search semantic ranker
            { name: 'AUTH_ENABLED', value: 'true' }
            { name: 'CORS_ALLOW_ORIGINS', value: corsAllowOrigins }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

output apiFqdn string = api.properties.configuration.ingress.fqdn
output apiPrincipalId string = api.identity.principalId
