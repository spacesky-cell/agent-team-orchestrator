/** Agent Team Orchestrator - Shared Types and Utilities */

// Subtask definition from task decomposition
export interface Subtask {
  id: string;
  name: string;
  role: string;
  dependencies: string[];
  expected_output: string;
}

// Task decomposition result
export interface TaskDecomposition {
  task_id: string;
  summary: string;
  subtasks: Subtask[];
}

// Role definition
export interface Role {
  id: string;
  name: string;
  description: string;
  expertise: string[];
  tools: string[];
  system_prompt: string;
  deliverables: Deliverable[];
}

// Deliverable format
export interface Deliverable {
  format: string;
  description: string;
}

// Team state
export interface TeamState {
  task_id: string;
  subtasks: Subtask[];
  artifacts: Record<string, unknown>;
  messages: unknown[];
  status: 'pending' | 'running' | 'completed' | 'failed';
  current_subtasks: string[];
}

// LLM Provider configuration
export interface LLMProvider {
  provider: 'anthropic' | 'openai' | 'ollama' | 'custom';
  model?: string;
  api_key?: string;
  base_url?: string;
  temperature?: number;
  max_tokens?: number;
}

// Task execution result
export interface TaskResult {
  task_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  current_subtask?: Subtask;
  artifacts: Record<string, unknown>;
  error?: string;
}
