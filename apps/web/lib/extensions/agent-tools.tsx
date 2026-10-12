// Extension points of the agent editor's tools tab.
//
// Keep managed integrations out of the custom tools list and render their
// catalog through this single extension point in the agent editor.

import type { ComponentType } from "react";
import type { AgentTool } from "@/types";
import { ComposioSection } from "@/components/composio/composio-section";

export type ManagedToolsSection = ComponentType<{
  agentId: string;
  /** The deployment changed the agent's tools; the editor reloads its list. */
  onToolsChange: () => void;
}>;

export const agentToolsExtensions: {
  /** True for a tool the deployment manages elsewhere: hidden from the custom list, still counted. */
  isManaged: (tool: AgentTool) => boolean;
  /** Rendered under the custom tools list, or nothing. */
  ManagedSection: ManagedToolsSection | null;
} = {
  isManaged: (tool) => /^c[1-9][0-9]?$/.test(tool.name) && tool.description.startsWith("Composio: "),
  ManagedSection: ComposioSection,
};
