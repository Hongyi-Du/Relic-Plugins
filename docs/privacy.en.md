# Privacy and local data

[中文](privacy.zh-CN.md)

The plugin stores organization messages, documents, tasks, membership, episodes, protocols and runtime receipts locally in SQLite. Bridge may also save seat environment configuration and approved trajectory exports. These records can contain private work and credentials supplied by a user; keep their directories and backups private.

The runtime does not contain its own model service, API key, analytics endpoint or hosted organization database. When a configured member starts a turn, its host application receives the prompt and uses that account's normal provider, permissions and billing. Shared messages become visible to the members addressed by the organization workflow. The local store is not an access-control boundary against another program running as the same operating-system user.

Bridge trajectory access is a separate request/approval workflow. Approved exports may include full prompts, responses, tool arguments/results, reasoning records present in the source transcript, and session-attributable memory. Redaction is enabled by default, but personal text and unusual secrets may remain. Inspect an export before sending it outside the organization. `memory:false` excludes memory when making a request; never use `redact:false` casually.

Only session-associated Codex memory can be attributed to a requested session. Shared Claude project memory is not exported as if it belonged to one session. Replacing a seat retains shared organization records, while the previous carrier's private note state does not become the new carrier's notes.

Removing the plugin does not erase the database, transcripts, host sessions or exports. To discard records, stop plugin processes and explicitly remove the intended local data after backing up anything needed. Do not publish the data directory, `.relic-seat.json`, runtime receipts or entire transcripts in a GitHub issue. Report security-sensitive findings privately using the contact information on [Hongyi Du's website](https://hongyidu.ai).
