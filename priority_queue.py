import heapq
import time


class PriorityQueue:
    def __init__(self):
        self.heap = []
        self.entry_finder = {}
        self.REMOVED = '<removed>'
        self.counter = 0

    def push(self, priority, task):
        if task in self.entry_finder:
            self.remove(task)
        entry = [priority, self.counter, task]
        self.counter += 1
        self.entry_finder[task] = entry
        heapq.heappush(self.heap, entry)

    def remove(self, task):
        entry = self.entry_finder.pop(task)
        entry[-1] = self.REMOVED

    def pop(self):
        while self.heap:
            priority, count, task = heapq.heappop(self.heap)
            if task is not self.REMOVED:
                del self.entry_finder[task]
                return priority, task
        raise KeyError('pop from an empty priority queue')

    def __len__(self):
        return len(self.entry_finder)


if __name__ == '__main__':
    x = time.time()
    pq = PriorityQueue()
    pq.push(1, 'x')
    pq.push(3, 'y')
    for _ in range(1000000 // 3):
        pq.push(2, 'z')
        pq.push(1, 'y')
        pq.push(5, 'x')

    pq.push(4, 'x')

    while len(pq):
        print(pq.pop())
    print(f'Time taken: {time.time() - x}')
