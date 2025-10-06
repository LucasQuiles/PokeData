# AGENT PROTOCOLS

## Release Gate: Launcher Syntax Integrity
- Before pushing or handing off changes, run `./pokedata --help` (or any short launcher invocation) to ensure the shell script still parses cleanly.
- If the launcher fails to execute due to a syntax error (e.g., heredoc/`then` mismatches), treat it as a release blocker: fix immediately, re-run the check, and document the fix in the PR/commit summary.
- CI/peer review should reject any contribution that breaks the launcher entrypoint, since it is the primary interface for collaborators and operators.

## Release Gate: Dependency Self-Test
- Prior to tagging a release/PR that modifies bootstrap or dependency logic, run `./pokedata --no-browser` to confirm the launcher can resolve Python/system dependencies without manual intervention.
- Any missing dependency warning must include remediation guidance (e.g., Homebrew commands) so the operator can act immediately.
- Do not ship changes that regress automatic dependency recovery (virtualenv provisioning or Homebrew auto-install attempts).
