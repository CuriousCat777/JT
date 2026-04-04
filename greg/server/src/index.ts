import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { registerCredenceTools } from "./agents/credence.js";
import { registerFormaTools } from "./agents/forma.js";
import { registerComplyTools } from "./agents/comply.js";
import { registerVitalsTools } from "./agents/vitals.js";
import { registerLedgerTools } from "./agents/ledger.js";
import { registerNexusTools } from "./agents/nexus.js";

const server = new McpServer({
  name: "greg",
  version: "0.1.0",
  description:
    "GREG — AI Agent Platform for Physician Practice Establishment. Guiding Regulations, Establishment & Growth.",
});

// Register all agent tools
registerCredenceTools(server);
registerFormaTools(server);
registerComplyTools(server);
registerVitalsTools(server);
registerLedgerTools(server);
registerNexusTools(server);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("GREG MCP Server running on stdio");
}

main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});
