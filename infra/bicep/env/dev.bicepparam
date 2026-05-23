using '../main.bicep'

param namePrefix = 'compliance'
// Set to your ACR image (build + push the api via infra/compose/Dockerfile.api).
param apiImage = '<your-acr>.azurecr.io/compliance-api:latest'
param tags = {
  app: 'ai-compliance-nlweb'
  profile: 'azure'
  env: 'dev'
}
