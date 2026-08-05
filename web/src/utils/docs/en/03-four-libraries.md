# 3. Four Libraries

The four libraries are the capability foundation that sets Soulprout apart from ordinary AI tools.

---

## 3.1 Expert Library (Agents)

Create, manage, and reuse AI agents.

### What makes up an agent

| Parameter | Description |
|---|---|
| **Type** | Main agent (orchestrates) / sub-agent (focused subtasks) |
| **Model** | Pick the best model for the job |
| **System prompt** | Role, capabilities, workflow, and output rules |
| **Tools** | Tools this agent may use |
| **Knowledge bases** | Dedicated reference materials |
| **Skills** | Skill packs that add professional execution ability |
| **Sub-agents** | Subordinates the main agent can dispatch |

### Main agent vs sub-agent

**Sub-agent**: A specialist for one step — e.g. “data collector” or “copywriter”.  
**Main agent**: The project manager — breaks down work, dispatches, and integrates results.

### How to create an agent

**Option 1: Auto-generate via Expert mode (recommended)**  
Describe the business need → confirm details → the team is planned and saved to the expert library.

**Option 2: Create manually**  
Click **+**, fill in name and prompt, configure model / tools / knowledge / skills, then save.

---

## 3.2 Knowledge Library (Knowledges)

Your **materials hub** for large document collections you want to reuse long-term.

### Knowledge base vs direct file upload

| Scenario | Prefer |
|---|---|
| Many messy materials; you only need relevant snippets | Knowledge base |
| Few files (1–3) that the AI should understand in full | Direct upload |

### Two retrieval modes

| Mode | Best for |
|---|---|
| **RAG fast retrieval** | Simple lookup and Q&A |
| **AI knowledge retrieval agent** | Complex analysis and deep mining of materials |

---

## 3.3 Tool Library (Tools)

Gives agents the ability to **actually do things**. Common capabilities:

- **Files**: Read, write, and edit documents/code; understand images
- **Execution**: Run Shell / Python / Node commands in the workspace
- **Web**: Search and fetch pages
- **Collaboration**: Create experts, call sub-agents, blueprint planning
- **Memory & knowledge**: Memory CRUD, knowledge retrieval and management
- **Skills & context**: Load skills; compress or clear conversation context
- **Interaction**: Ask you batch questions to confirm details

You usually don’t pick tools manually — Soulprout calls what the task needs. When creating an agent, you can also bind tools precisely to limit its scope.

---

## 3.4 Skill Library (Skills)

A Skill is a reusable professional capability pack (scripts, workflows, best practices, etc.). Once loaded, the agent can follow that domain’s playbook instead of starting from scratch every time.

The system ships with about **60** built-in skills across documents, data analysis, research, marketing, teaching, development, and more. You can also **upload personal skills** and bind them to agents (personal skills take priority over system skills).

---

*Next: [4. Soul Mode](04-soul-mode.md)*
