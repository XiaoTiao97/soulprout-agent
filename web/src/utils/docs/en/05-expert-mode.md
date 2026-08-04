# Expert Mode

Expert mode is for complex business work — multi-agent collaboration to deliver high-quality results.

In **Task mode**, click **“Customize your Agent expert/team”** to start creating an expert.

---

## 5.1 What is Expert Mode?

For complex jobs, Soulprout doesn’t leave a single AI to fight alone. It:

1. **Analyzes the task**: Complexity and required capabilities  
2. **Builds a team**: Matches specialist agents to subtasks  
3. **Works in parallel**: Multiple experts run at once  
4. **Integrates the output**: The main agent delivers a complete result  

### Expert mode vs Task mode

| | Task mode | Expert mode |
|---|---|---|
| **Best for** | Simple Q&A, single-step jobs | Complex projects, multi-step workflows |
| **How it works** | One AI | Multiple AIs in parallel |
| **Efficiency** | Serial | Parallel |
| **Quality** | Depends on one model | Specialists combine strengths |
| **Transparency** | Simpler process | Plan / Tools / SubAgents fully visible |
| **Reusability** | One-off | Expert teams saved and iterated |

---

## 5.2 Build an Expert Team in 5 Minutes

Example: a “fund screening assistant”.

#### Step 1: Describe the need

```
I want a short-term fund screening assistant that finds recently strong-performing funds.
```

#### Step 2: Confirm details interactively

Soulprout clarifies period, sectors, metrics, output format, and more — then plans. Alignment first prevents answering the wrong question.

#### Step 3: AI plans the expert team

| Role | Responsibility | Config |
|---|---|---|
| **Main agent** Fund screening hub | Orchestrate flow, integrate output | Strong reasoning model |
| **Sub-agent 1** Market scout | Search policy and industry hotspots | web_search |
| **Sub-agent 2** Fund data hunter | Fetch fund info and performance | Financial data tools |
| **Sub-agent 3** Short-term momentum analyst | Analyze recent trends and momentum | Data analysis tools |
| **Sub-agent 4** Holistic evaluator | Combine findings into recommendations | Strong synthesis model |

#### Step 4: Confirm and generate

Models, tools, prompts, and call relationships are configured automatically and saved to the expert library. All through conversation — no code.

#### Step 5: Use immediately

Pick the main agent from the expert library and assign a task. Sub-agents run in parallel; the main agent returns the result.

---

## 5.3 How Expert Teams Work

```
User
  ↓ request
Main agent (orchestrator)
  ↓ decompose
┌─────────┬─────────┬─────────┐
│ Sub 1   │ Sub 2   │ Sub 3   │
│ parallel│ parallel│ parallel│
└─────────┴─────────┴─────────┘
  ↓ aggregate
Main agent (integrate)
  ↓ final report
User
```

- **Main agent**: Sees the whole picture, decomposes work, guards quality — not a mere relay  
- **Sub-agents**: Own models and tools; run in parallel without interfering  
- **Full transparency**: Watch status and tool calls on the right; intervene anytime  

---

## 5.4 Customize Your Expert Team

Auto-generated teams can be edited anytime in the expert library:

| Parameter | Tip |
|---|---|
| **Model** | Reasoning / creative / lightweight as needed |
| **System prompt** | Tighten role, SOP, and output format |
| **Tools / knowledge / skills** | Bind precisely; limit the boundary |
| **Sub-agents** | Add or remove members |

Teams stay in the expert library permanently — call them anytime and keep iterating.

---

*Next: [Open Source & Private Deployment](06-open-source.md)*
