# Archivist Public-Demo Deployment

This runbook deploys Archivist as a single public Render web service while keeping the manuscript,
typeset PDF, chunks, and Chroma index out of GitHub. Cromblog is the public doorway; the Archivist
service runs separately and can later use a custom subdomain such as `archivist.cromblog.com`.

## Prepared architecture

- Render Hobby workspace
- one paid Starter web-service instance
- one 1 GB persistent disk mounted at `/var/data`
- one Uvicorn worker and one service instance
- trusted Render proxy headers so the in-memory per-reader gate sees the forwarded client address
- server-selected `public_demo` exposure profile
- private full-corpus runtime bundle copied to the disk after deployment
- OpenAI key stored only as a Render secret
- application-enforced monthly OpenAI budget and request limits

The repository-root `render.yaml` is the source of truth for the service configuration. Automatic
deploys are disabled initially so a source-code push cannot unexpectedly replace the running
version.

## Files that stay private

Never commit or upload these files as source:

- the DOCX manuscript;
- the typeset PDF;
- `output/chunks.json`;
- `chroma_db/`;
- `.env`;
- API keys;
- the generated runtime archive under `runtime/`.

The generated archive contains only the pruned 481-record Chroma collection, the matching private
chunk file, and a text-free identity manifest. It does not contain the original DOCX or PDF. It is
still private manuscript infrastructure and must not be attached to a public release.

Current prepared bundle:

| Property | Value |
|---|---|
| Local path | `runtime/archivist-public-runtime.tar.gz` |
| SHA-256 | `37642f9d495d93834829d0749d2c25389c069bd160caf438bbc34b6c2f4ad78f` |
| Size | 3,274,947 bytes |
| Chroma collection | `manuscript` |
| Embedded records | 481 |
| Chunks SHA-256 | `02e87cd42dc366a04f4b1ec43936599475cf18d120e26ce729da482a5949d6cc` |
| Corpus-manifest SHA-256 | `b7ff94315a3f1f28c831e2c3ca62c385567d2b1447c19ff45139d175c3ff3c17` |

Regenerate the archive only after the live corpus changes:

```powershell
uv run python scripts/build_public_runtime_bundle.py
```

The builder refuses to overwrite an existing archive. Move the old archive to a safe private
location before deliberately building a replacement.

## Owner setup in Render

These are the first steps that require the owner's Render account and billing method:

1. Sign in to Render with GitHub.
2. Keep the free Hobby workspace.
3. Grant Render access to `mcrombie/archivist` only.
4. Add a billing method.
5. Select **New > Blueprint**, choose `mcrombie/archivist`, and use the repository-root
   `render.yaml`.
6. Review the proposed Starter service and 1 GB disk before creating either resource.
7. Enter `OPENAI_API_KEY` directly in Render when the Blueprint asks for the unsynchronized
   secret. Never paste it into source control, a screenshot, or chat.

The Blueprint sets the public OpenAI ceiling to `$5.00` per calendar month. Change
`ARCHIVIST_PUBLIC_MONTHLY_BUDGET_USD` in Render only as a deliberate owner decision. Render
hosting charges are separate from OpenAI usage.

## Seed the private disk

The first source deployment can become live before its private corpus is present:

- `GET /api/live` should return `200`;
- `GET /api/health` should return `503` until the disk is seeded.

Render's dashboard shows the service-specific SSH command. Use that exact destination to copy the
private archive to `/var/data`; do not record the destination or SSH details in the repository.
From this repository, the transfer has this shape:

```powershell
scp -s runtime/archivist-public-runtime.tar.gz <render-ssh-destination>:/var/data/
```

Then open the Render Shell and extract it:

```sh
cd /var/data
sha256sum archivist-public-runtime.tar.gz
tar -xzf archivist-public-runtime.tar.gz
```

The reported archive hash must exactly match the value in this runbook. Confirm that
`/var/data/runtime_bundle.json`, `/var/data/output/chunks.json`, and
`/var/data/chroma_db/` exist. Restart the service from the Render dashboard after extraction so
the process opens the newly seeded Chroma store cleanly.

## Readiness and anonymous release checks

After restart:

1. `GET /api/live` returns `200` with `{"status":"live"}`.
2. `GET /api/health` returns `200` with `{"status":"ready"}`.
3. `GET /api/config` reports the `public_demo` profile, 481 searchable and embedded chunks,
   `full_source_text: false`, and `public_page_locators: true`.
4. The opening page loads from the service's HTTPS `onrender.com` URL.
5. One neutral question returns an answer with edition-qualified Typeset PDF page locators.
6. Source cards expose no full chunk text, chunk IDs, physical PDF pages, or internal diagnostics.
7. `/docs`, `/openapi.json`, project-management, embedding, source-file, and cost-setting routes
   return `404`.
8. A request containing `n_results` or `allow_over_budget` returns `422`.
9. A request larger than the public body limit returns `413`.
10. Repeated requests eventually return `429` and a `Retry-After` header.

Do not connect Cromblog until all ten checks pass on the deployed URL.

## Connect Cromblog

Cromblog is prepared to discover the demo URL at build time:

```text
NEXT_PUBLIC_ARCHIVIST_URL=https://<render-service>.onrender.com
```

Set that value in Cromblog's existing hosting environment and rebuild Cromblog. Its featured
Archivist panel and Projects entry will then expose an **Open live demo** link. Without the
variable, the panel honestly links to the Archivist project record and says **Deployment ready**.

The initial Render URL is sufficient. A custom `archivist.cromblog.com` domain is a later,
optional DNS step and should be attempted only after the generated Render URL is stable.

## Operational limits

- The persistent disk restricts Archivist to one Render service instance.
- The in-memory rate/concurrency gate is intentionally correct only for that one-instance design.
- The service is not directly internet-reachable behind Render's proxy; Uvicorn trusts that
  proxy's forwarded client address for per-reader rate limiting.
- The app's monthly OpenAI ceiling is enforced by a ledger stored under `/var/data/runtime/`.
- The public UI does not expose the ledger, model diagnostics, or budget bypass controls.
- The typeset page locators apply only to `Typeset PDF (July 6, 2026)`.
- Conversation history lasts for the open browser page and is not a durable account feature.
- Deployment does not make Archivist a general-purpose chatbot; it remains a conversation with
  one book.

If the Starter instance proves too memory-constrained, inspect the failure before changing its
instance type. An upgrade is a separate hosting-cost decision, not an automatic deployment step.
