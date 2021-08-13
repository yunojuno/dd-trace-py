def test_trace(run_memory_leak_test):
    run_memory_leak_test(
        """
from ddtrace import tracer

for _ in range(10):
    with tracer.trace("root"):
        for i in range(50):
            with tracer.trace("child"):
                pass

tracer.writer.stop()
        """
    )
