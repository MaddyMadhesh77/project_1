import asyncio
import time

from app.services.embedding import EmbeddingService


class _SlowModel:
    def encode(self, text, normalize_embeddings):
        time.sleep(0.3)  # stands in for a CPU-bound forward pass

        class _Vec:
            def tolist(self):
                return [0.0]

        return _Vec()


async def test_aembed_does_not_block_the_event_loop():
    # Regression (audit A9): encode() ran synchronously inside async routes,
    # stalling every other request for the duration of the forward pass.
    service = EmbeddingService.__new__(EmbeddingService)
    service._model = _SlowModel()

    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    assert await service.aembed("x") == [0.0]
    task.cancel()

    assert ticks >= 10  # the loop kept running while the model "worked"
