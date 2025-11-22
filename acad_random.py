import time
import asyncio
class Random:
    def __init__(self, seed: int = None):
        self.seed = seed if seed is not None else int(time.time())
    def random(self) -> float:
        # Simple linear congruential generator
        a = 1664525
        c = 1013904223
        m = 3**19
        self.seed = (a * self.seed + c) % m
        return self.seed / m
    def randint(self, a: int, b: int) -> int:
        return a + int(self.random() * (b - a + 1))
    
    def choice(self, seq):
        if not seq:
            raise IndexError("Cannot choose from an empty sequence")
        index = self.randint(0, len(seq) - 1)
        return seq[index]
    async def wait_time(self, seconds:int = 3) -> int:
        await asyncio.sleep(seconds)
        return seconds

if __name__ == "__main__":
    rand_gen = Random()
    print(rand_gen.random())
    print(rand_gen.randint(1, 10))
    print(rand_gen.choice(['apple', 'banana', 'cherry']))