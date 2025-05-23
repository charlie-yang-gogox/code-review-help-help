# GitHub Code Review Help Help 🤖

This project automatically monitors GitHub pull requests across multiple repositories and sends a structured summary to a Slack channel.  
It’s designed to help teams stay on top of PR review progress, with clear visual indicators.

## 🔧 Features

- Fetches open pull requests from multiple GitHub repositories
- Displays review status of each PR in Slack:
  - ✅ **Ready for Merge** – 2 or more approvals
  - 🕐 **Pending Reviews**
- Shows reviewer statuses using emoji:
  - ✔️ approved
  - ❌ changes requested
  - 🗨️ commented
  - ⏳ pending
  - 🚫 dismissed
- Groups PRs by repository with clear headings