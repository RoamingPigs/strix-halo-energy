"""llama-server b10970 answers HTTP 500 when the generated text holds invalid UTF-8, after the generation has finished.
The harness must recover the timings from the server log, and must still fail on anything else."""
import http.server
import json
import pathlib
import sys
import threading

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "harness"))
import warden_study as ws  # noqa: E402

# Real lines from a failed request (ROCm run, 2026-10-12), kept verbatim.
LOG = (
    "6.11.306.283 I slot print_timing: id  0 | task 589 | prompt eval time =      63.00 ms /     2 tokens (   31.50 ms per token,    31.75 tokens per second)\n"
    "6.11.306.286 I slot print_timing: id  0 | task 589 |        eval time =    9287.27 ms /   512 tokens (   18.17 ms per token,    55.02 tokens per second)\n"
    "6.11.306.286 I slot print_timing: id  0 | task 589 |       total time =    9350.27 ms /   514 tokens\n"
)
PARSE_500 = {"error": {"code": 500, "message": "The model produced output that does not match the expected Content-only format", "type": "server_error"}}


def serve(status, body, before_reply=lambda: None):
    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            before_reply()   # the real server logs its timings before it answers
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture
def harness(tmp_path, monkeypatch):
    log = tmp_path / "server.log"
    log.write_text("earlier request\n6.0.0.0 I slot print_timing: id  0 | task 1 |        eval time =       1.00 ms /     9 tokens\n")
    monkeypatch.setattr(ws, "SERVER_LOG", log)
    started = []

    def run(status, body, append=LOG, n=512):
        def write_log():
            with open(log, "a") as f:
                f.write(append)
        srv = serve(status, body, write_log)
        started.append(srv)
        monkeypatch.setattr(ws, "PORT", srv.server_address[1])
        return ws.completion([1, 2, 3], n)
    yield run
    for s in started:
        s.shutdown()


def test_parser_reads_the_last_request_only():
    tm = ws.timings_from_server_log(LOG)
    assert tm["predicted_n"] == 512 and tm["prompt_n"] == 2
    assert tm["predicted_ms"] == pytest.approx(9287.27) and tm["predicted_per_second"] == pytest.approx(512 / 9.28727)


def test_parse_error_recovers_timings_and_flags_it(harness):
    t_send, t_recv, tm, _, _ = harness(500, PARSE_500)
    assert tm["predicted_n"] == 512 and tm["parse_error"] is True
    assert tm["predicted_per_second"] == pytest.approx(55.12, abs=0.1)
    assert t_recv >= t_send


def test_normal_reply_is_unchanged(harness):
    reply = {"timings": {"prompt_n": 2, "prompt_ms": 63.0, "predicted_n": 512, "predicted_ms": 9000.0, "predicted_per_second": 56.9, "cache_n": 4000},
             "tokens_predicted": 512, "tokens_cached": 4514}
    _, _, tm, _, cached = harness(200, reply, append="")
    assert tm["predicted_per_second"] == 56.9 and "parse_error" not in tm and cached == 4514


def test_other_500_still_fails(harness):
    with pytest.raises(ws.CellFailed):
        harness(500, {"error": {"code": 500, "message": "out of memory"}})


def test_parse_error_without_timings_still_fails(harness, monkeypatch):
    monkeypatch.setattr(ws.time, "sleep", lambda s: None)
    with pytest.raises(ws.CellFailed):
        harness(500, PARSE_500, append="nothing useful\n")


def test_parse_error_with_short_generation_still_fails(harness):
    # The server stopped early: the window would be wrong, so the cell must not be accepted.
    short = LOG.replace("/   512 tokens (   18.17", "/   200 tokens (   18.17")
    with pytest.raises(ws.CellFailed):
        harness(500, PARSE_500, append=short)
