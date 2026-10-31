# aioengieromania

Async Python client for MyENGIE România accounts (the API behind the MyENGIE mobile
app). It powers the [ENGIE România](https://github.com/coffeerunhobby/ha-engie) Home
Assistant integration.

Unofficial; not affiliated with or endorsed by ENGIE.

## Usage

```python
import aiohttp
from aioengieromania import EngieClient

async with aiohttp.ClientSession() as session:
    client = EngieClient("user@example.com", "password", device_id="<a stable uuid>", session=session)
    for place in await client.async_get_places():
        point = await client.async_get_point(place)
        print(place.address, point.amount_due, [m.last_index for m in point.meters])
```

`device_id` identifies your client to ENGIE the way the app's device id does; keep it
stable per installation. Payments are per client rather than per place:
`await client.async_get_payments(place.pa)`.

`async_submit_index(point, meter, index)` reports a self-read meter index. ENGIE only
accepts it inside the meter's self-reading window (`meter.self_read_open(today)`);
a refusal raises `EngieRejectedError` carrying ENGIE's reason.

Errors: `EngieAuthError` (credentials rejected), `EngieConnectionError` (unreachable or
timed out), `EngieRejectedError` (a submission was refused), all subclasses of
`EngieError`.

## License

MIT
