# Composio integrations

The integration catalog lets an agency install a connector once and then connect a separate external account for each client. An agent only receives the individual actions selected for it. OAuth tokens remain with Composio; OpenLivery stores the connected-account ID and an encrypted MCP session header. A connection is never shared across clients.

## Configure the server

1. Create a Composio project and copy its API key into your secret manager.
2. Set `COMPOSIO_API_KEY` **only on the API service**. Do not set it on the web service, expose it through a `NEXT_PUBLIC_` variable, or commit it to Git.
3. Set `FRONTEND_URL` on the API service to the public HTTPS origin of OpenLivery, such as `https://app.example.com`. Composio returns to `/api/composio/oauth/callback` on that origin.
4. Run the new database migration (`alembic upgrade head`) and restart the API and web services. The normal Docker API start command already runs migrations.

For a Coolify Docker Compose deployment, the API service must explicitly receive the secret. In the Compose service definition, add:

```yaml
services:
  api:
    environment:
      COMPOSIO_API_KEY: ${COMPOSIO_API_KEY:-}
      FRONTEND_URL: https://app.example.com
```

Enter the actual key in Coolify's environment-variable editor, not in the Compose source. Make it a runtime secret, not a Docker build argument. Keep the production Compose file and its domain configuration under your own deployment overlay so upstream repository syncs do not replace them. The API and web containers need outbound HTTPS access to Composio and the connected providers; only the existing public OpenLivery origin needs inbound access.

The key is optional for startup: without it, the catalog shows a setup notice and does not call Composio. Add the key in Coolify before testing a provider authorization flow.

## Use the catalog

Open an agent's **Tools** tab, browse and install a connector for the agency, then connect the current client's account through the provider authorization screen. Finally, select the actions this agent may use. Read-only actions are selected by default when available; write and delete actions require explicit selection. A connected client account can be assigned to several agents belonging to that same client, each with a different action list.

Disconnecting a client account removes that connector from all of the client's agents and asks Composio to revoke the connection. Deleting the client also revokes its Composio accounts before local records are removed. If Composio is unavailable at deletion time, retry after it is reachable so external access is not orphaned.

Existing custom HTTP and MCP tools remain available. The catalog uses the existing agent-tools extension point; it does not replace the core tool runner. The Composio API key is a server-level credential, so anyone with access to that key or its Coolify environment can manage every client connection in this installation.

## Limits

- The catalog currently supports Composio's managed authorization flow. Connectors requiring your own OAuth application or other custom auth setup need additional configuration and may not connect with this flow.
- An agent can select up to 20 actions per connector. Action names longer than the model-provider tool-name limit are unavailable.
- A production OAuth round trip must be verified with a real Composio project and one test provider account before enabling client accounts. Automated tests mock Composio and do not prove provider-side authorization.
