#!/usr/bin/env python3
"""测试插件系统修复"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.orchestration.package_resolver import PackageSpecifier

def test_dynamic_branch_detection():
    """测试动态分支检测"""
    print("=" * 60)
    print("测试动态分支检测功能")
    print("=" * 60)

    test_cases = [
        {
            'input': 'alchaincyf/darwin-skill',
            'expected_ref': 'master',
            'desc': '无分支指定，应动态获取 master'
        },
        {
            'input': 'obra/superpowers',
            'expected_ref': 'main',
            'desc': '无分支指定，应动态获取 main'
        },
        {
            'input': 'obra/superpowers@develop',
            'expected_ref': 'develop',
            'desc': '用户指定 develop，应使用 develop'
        },
        {
            'input': 'alchaincyf/darwin-skill@master',
            'expected_ref': 'master',
            'desc': '用户指定 master，应使用 master'
        },
        {
            'input': 'https://github.com/obra/superpowers',
            'expected_ref': 'main',
            'desc': 'GitHub URL 无分支指定，应动态获取'
        },
        {
            'input': 'https://github.com/alchaincyf/darwin-skill#master',
            'expected_ref': 'master',
            'desc': 'GitHub URL 指定分支'
        },
    ]

    passed = 0
    failed = 0

    for i, case in enumerate(test_cases, 1):
        print(f"\n测试 {i}: {case['input']}")
        print(f"说明: {case['desc']}")

        try:
            spec = PackageSpecifier.parse(case['input'])
            if spec.ref == case['expected_ref']:
                print(f"✓ 通过: ref={spec.ref}")
                passed += 1
            else:
                print(f"✗ 失败: 期望 ref={case['expected_ref']}, 实际 ref={spec.ref}")
                failed += 1
        except Exception as e:
            print(f"✗ 异常: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    return failed == 0

if __name__ == '__main__':
    success = test_dynamic_branch_detection()
    sys.exit(0 if success else 1)
