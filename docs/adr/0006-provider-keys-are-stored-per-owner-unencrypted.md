# Provider API keys are stored per owner in the database, unencrypted

Each user's Provider API keys are entered on the Settings page and stored in the application database with the user's `owner_id`. They are stored as plain text. The app is self-hosted for now, and anyone who can read its database is already on the user's own machine, along with any secret that would be used to decrypt the keys. Encryption would therefore protect almost nothing while adding a secret that every installation has to generate and keep. We chose the database over environment variables so that a new self-hoster sets the app up from its own UI without editing files, and so that keys can be added or replaced without a restart. Keys are per owner, not global, so the app can still become a hosted service later without a shared key leaking across users.

## Consequences

- Keys never leave the backend in full: the API returns them masked.
- The environment no longer holds any API key or model setting. A key left in an old `.env` is ignored and must be entered once in Settings.
- Hosting the app for other people would first require encrypting the stored keys (a one-off migration) as well as login. Nothing stored now has to change shape for that.
