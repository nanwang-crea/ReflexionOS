"""
测试文件示例
包含基本的单元测试用例
"""
import unittest


def add(a, b):
    """加法函数"""
    return a + b


def subtract(a, b):
    """减法函数"""
    return a - b


def multiply(a, b):
    """乘法函数"""
    return a * b


class TestMathOperations(unittest.TestCase):
    """数学运算测试类"""

    def test_add(self):
        """测试加法"""
        self.assertEqual(add(2, 3), 5)
        self.assertEqual(add(-1, 1), 0)
        self.assertEqual(add(0, 0), 0)

    def test_subtract(self):
        """测试减法"""
        self.assertEqual(subtract(5, 3), 2)
        self.assertEqual(subtract(0, 0), 0)
        self.assertEqual(subtract(-1, -1), 0)

    def test_multiply(self):
        """测试乘法"""
        self.assertEqual(multiply(2, 3), 6)
        self.assertEqual(multiply(-1, 5), -5)
        self.assertEqual(multiply(0, 100), 0)


if __name__ == '__main__':
    unittest.main()
