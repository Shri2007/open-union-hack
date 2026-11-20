# Open Union Firedrill recipes

The **Open Union relay drills** world runs the simulated `sybil` and `trap-offers` task scenarios once each. Firedrill uses its HTTP driver to call the local adapter, which calls the live relay at `127.0.0.1:8077`. The reset hook creates a fresh `drill-*` coalition through the Open Union store for each drill. It leaves the demo coalition and past drill evidence intact.

From the running relay checkout, with its Python virtual environment active:

```sh
plan=$(mktemp)
python firedrill/plan.py 66db90945062cf1f4f5bc8b187958edba3bb0b3c602ec4e786d3135b137fb500 > "$plan"
firedrill status --plan "$plan"
firedrill plan --world 7f4d53ae-e5ce-487d-a81a-7702ed8fe42e
```

After approving the review, use the reported IDs in these commands:

```sh
firedrill apply <plan-id> --approve --follow
firedrill runner enroll
firedrill run --plan "$plan" --descriptor firedrill/descriptor.json --campaign <campaign-id>
firedrill report <campaign-id>
```

The descriptor's source-root identity binds it to this checkout. The scenario and world JSON reference versions in the signed-in Firedrill workspace.

The join drill checks counts after every simulated join. The offer drill submits 20 fixtures to `POST /offers/check` using `coalition_id`, `price_cents`, and `terms_text` and reads the top-level `verdict`. A trap passes the drill if the checker rejects it or asks for human review. A clean control must receive `pass`. An unavailable route yields a labeled stub with no score.
