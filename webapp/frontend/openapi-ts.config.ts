import { defineConfig } from '@hey-api/openapi-ts'

// Generates the API client in src/api from the backend's OpenAPI schema.
// Run `npm run generate-api` after changing the backend's HTTP API.
export default defineConfig({
  input: 'openapi.json',
  output: 'src/api',
  // The API is served from the same origin, under /api
  plugins: [{ name: '@hey-api/client-fetch', baseUrl: false }, '@tanstack/react-query'],
})
