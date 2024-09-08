import pytest
from priority_queue import PriorityQueue


class TestPriorityQueue:
    def test_one_element(self):
        pr = PriorityQueue()
        pr.push(1, 'x')
        assert pr.pop() == (1, 'x')

    def test_multiply_elements(self):
        pr = PriorityQueue()
        pr.push(3, 'x')
        pr.push(1, 'y')
        pr.push(2, 'z')
        assert pr.pop() == (1, 'y')
        assert pr.pop() == (2, 'z')
        assert pr.pop() == (3, 'x')

    def test_similar_elements(self):
        pr = PriorityQueue()
        pr.push(2, 'x')
        pr.push(1, 'x')
        assert pr.pop() == (1, 'x')

    def test_len(self):
        pr = PriorityQueue()
        pr.push(1, 'x')
        pr.push(2, 'x')
        assert len(pr) == 1
        pr.push(3, 'r')
        assert len(pr) == 2

    def test_fail_pop(self):
        pr = PriorityQueue()
        try:
            pr.pop()
            assert False
        except KeyError:
            assert True
