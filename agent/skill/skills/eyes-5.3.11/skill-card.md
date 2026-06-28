## Description: <br>
Eyes monitors global news and market-moving events, classifies their severity, analyzes likely market impact across sectors, currencies, and commodities, and can send scheduled hot-topic digests. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[kobenfang](https://clawhub.ai/user/kobenfang) <br>

### License/Terms of Use: <br>
MIT-0 <br>


## Use Case: <br>
External users and market-focused agents use this skill to produce global-news summaries, prioritize events by urgency, and draft market-impact analysis for A-share, Hong Kong, and U.S. market themes. It can also help configure recurring ClawHub/OpenClaw news digests for selected delivery channels. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill can send messages to configured channels and may include example or inherited routing targets. <br>
Mitigation: Review and replace channel and target values before enabling delivery, especially any Feishu example target or BigA shared configuration. <br>
Risk: The skill can create recurring cron jobs that send automated news digests. <br>
Mitigation: Confirm the cron schedule, timeout, channel, and recipient before installation, and keep a clear process for disabling jobs if messages are misrouted. <br>
Risk: News and market-impact summaries may be incomplete, stale, or overly confident for investment decisions. <br>
Mitigation: Treat generated analysis as informational triage and verify material facts, market data, and investment implications against authoritative sources before acting. <br>


## Reference(s): <br>
- [ClawHub skill page](https://clawhub.ai/kobenfang/eyes) <br>
- [Event impact matrix](artifact/references/event-impact-matrix.md) <br>
- [User preference reference](artifact/references/user-preferences.md) <br>
- [Cron templates](artifact/references/cron-templates.json) <br>
- [Cron install shell template](artifact/references/cron-install-shell.sh) <br>


## Skill Output: <br>
**Output Type(s):** [text, markdown, shell commands, configuration, guidance] <br>
**Output Format:** [Markdown news digests and market-impact summaries, with optional JSON utility output and shell commands for message delivery or cron setup.] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Scheduled or manual runs may segment long Markdown digests before delivery to configured messaging channels.] <br>

## Skill Version(s): <br>
5.3.11 (source: server-resolved release evidence) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
