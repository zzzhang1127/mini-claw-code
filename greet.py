"""
LeetCode 经典题目合集 (10道)
包含题目描述、解题思路和代码实现
"""

# ============================================
# 题目1: 两数之和 (Two Sum)
# 题目描述: 给定一个整数数组 nums 和一个整数目标值 target，
# 请你在该数组中找出和为目标值 target 的那两个整数，并返回它们的数组下标。
# ============================================
def two_sum(nums: list[int], target: int) -> list[int]:
    """
    解题思路：使用哈希表，将遍历过的数字存入字典，
    对于当前数字，检查 target - num 是否在字典中
    时间复杂度: O(n), 空间复杂度: O(n)
    """
    num_dict = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in num_dict:
            return [num_dict[complement], i]
        num_dict[num] = i
    return []


# ============================================
# 题目2: 反转链表 (Reverse Linked List)
# 题目描述: 给你单链表的头节点 head，请你反转链表，并返回反转后的链表
# ============================================
class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next

def reverse_list(head: ListNode) -> ListNode:
    """
    解题思路：使用三个指针，prev、curr、next_node
    遍历链表，将当前节点的next指向前一个节点
    时间复杂度: O(n), 空间复杂度: O(1)
    """
    prev = None
    curr = head
    while curr:
        next_node = curr.next
        curr.next = prev
        prev = curr
        curr = next_node
    return prev


# ============================================
# 题目3: 合并两个有序数组 (Merge Sorted Array)
# 题目描述: 给你两个按非递减顺序排列的整数数组 nums1 和 nums2，
# 另有两个整数 m 和 n，分别表示 nums1 和 nums2 中的元素数目。
# 请你合并 nums2 到 nums1 中，使合并后的数组同样按非递减顺序排列。
# ============================================
def merge(nums1: list[int], m: int, nums2: list[int], n: int) -> None:
    """
    解题思路：从后向前填充，避免覆盖 nums1 中的有效元素
    时间复杂度: O(m+n), 空间复杂度: O(1)
    """
    p1, p2, p = m - 1, n - 1, m + n - 1
    while p2 >= 0:
        if p1 >= 0 and nums1[p1] > nums2[p2]:
            nums1[p] = nums1[p1]
            p1 -= 1
        else:
            nums1[p] = nums2[p2]
            p2 -= 1
        p -= 1


# ============================================
# 题目4: 有效的括号 (Valid Parentheses)
# 题目描述: 给定一个只包括 '('，')'，'{'，'}'，'['，']' 的字符串 s，
# 判断字符串是否有效。有效字符串需满足：
# 1. 左括号必须用相同类型的右括号闭合
# 2. 左括号必须以正确的顺序闭合
# ============================================
def is_valid(s: str) -> bool:
    """
    解题思路：使用栈，遇到左括号入栈，遇到右括号检查栈顶是否匹配
    时间复杂度: O(n), 空间复杂度: O(n)
    """
    stack = []
    mapping = {')': '(', '}': '{', ']': '['}
    for char in s:
        if char in mapping:
            top = stack.pop() if stack else '#'
            if mapping[char] != top:
                return False
        else:
            stack.append(char)
    return not stack


# ============================================
# 题目5: 最大子数组和 (Maximum Subarray)
# 题目描述: 给你一个整数数组 nums，请你找出一个具有最大和的连续子数组
# （子数组最少包含一个元素），返回其最大和。
# ============================================
def max_sub_array(nums: list[int]) -> int:
    """
    解题思路：动态规划，dp[i]表示以第i个元素结尾的最大子数组和
    dp[i] = max(nums[i], dp[i-1] + nums[i])
    时间复杂度: O(n), 空间复杂度: O(1) - 可优化
    """
    max_sum = curr_sum = nums[0]
    for num in nums[1:]:
        curr_sum = max(num, curr_sum + num)
        max_sum = max(max_sum, curr_sum)
    return max_sum


# ============================================
# 题目6: 爬楼梯 (Climbing Stairs)
# 题目描述: 假设你正在爬楼梯。需要 n 阶你才能到达楼顶。
# 每次你可以爬 1 或 2 个台阶。你有多少种不同的方法可以爬到楼顶呢？
# ============================================
def climb_stairs(n: int) -> int:
    """
    解题思路：动态规划，dp[i] = dp[i-1] + dp[i-2]
    即到达第i阶的方法数 = 从i-1阶爬1步 + 从i-2阶爬2步
    时间复杂度: O(n), 空间复杂度: O(1) - 可优化
    """
    if n <= 2:
        return n
    prev2, prev1 = 1, 2
    for _ in range(3, n + 1):
        curr = prev1 + prev2
        prev2 = prev1
        prev1 = curr
    return prev1


# ============================================
# 题目7: 二叉树的中序遍历 (Binary Tree Inorder Traversal)
# 题目描述: 给定一个二叉树的根节点 root，返回它的中序遍历结果
# ============================================
class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right

def inorder_traversal(root: TreeNode) -> list[int]:
    """
    解题思路：递归实现中序遍历：左子树 -> 根节点 -> 右子树
    时间复杂度: O(n), 空间复杂度: O(h) h为树的高度
    """
    result = []
    def inorder(node):
        if node:
            inorder(node.left)
            result.append(node.val)
            inorder(node.right)
    inorder(root)
    return result


# ============================================
# 题目8: 对称二叉树 (Symmetric Tree)
# 题目描述: 给你一个二叉树的根节点 root，检查它是否轴对称
# ============================================
def is_symmetric(root: TreeNode) -> bool:
    """
    解题思路：递归比较左子树和右子树是否镜像对称
    时间复杂度: O(n), 空间复杂度: O(h)
    """
    def is_mirror(left, right):
        if not left and not right:
            return True
        if not left or not right:
            return False
        return (left.val == right.val and
                is_mirror(left.left, right.right) and
                is_mirror(left.right, right.left))
    
    if not root:
        return True
    return is_mirror(root.left, root.right)


# ============================================
# 题目9: 环形链表 (Linked List Cycle)
# 题目描述: 给你一个链表的头节点 head，判断链表中是否有环
# ============================================
def has_cycle(head: ListNode) -> bool:
    """
    解题思路：快慢指针，快指针每次走2步，慢指针每次走1步
    如果存在环，快指针最终会追上慢指针
    时间复杂度: O(n), 空间复杂度: O(1)
    """
    if not head or not head.next:
        return False
    slow = head
    fast = head.next
    while slow != fast:
        if not fast or not fast.next:
            return False
        slow = slow.next
        fast = fast.next.next
    return True


# ============================================
# 题目10: 最长公共前缀 (Longest Common Prefix)
# 题目描述: 编写一个函数来查找字符串数组中的最长公共前缀。
# 如果不存在公共前缀，返回空字符串 ""。
# ============================================
def longest_common_prefix(strs: list[str]) -> str:
    """
    解题思路：横向扫描，先比较前两个字符串的公共前缀，
    再用结果与下一个字符串比较
    时间复杂度: O(S) S为所有字符串字符总数, 空间复杂度: O(1)
    """
    if not strs:
        return ""
    prefix = strs[0]
    for s in strs[1:]:
        while not s.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix


# ============================================
# 测试代码
# ============================================
def test_all():
    """测试所有题目"""
    print("=" * 50)
    print("LeetCode 经典题目测试")
    print("=" * 50)
    
    # 测试1: 两数之和
    print("\n1. 两数之和:")
    nums = [2, 7, 11, 15]
    target = 9
    result = two_sum(nums, target)
    print(f"   nums={nums}, target={target}")
    print(f"   结果: {result} (nums[{result[0]}] + nums[{result[1]}] = {nums[result[0]]} + {nums[result[1]]} = {target})")
    
    # 测试2: 反转链表
    print("\n2. 反转链表:")
    head = ListNode(1, ListNode(2, ListNode(3, ListNode(4, ListNode(5)))))
    reversed_head = reverse_list(head)
    result_list = []
    while reversed_head:
        result_list.append(reversed_head.val)
        reversed_head = reversed_head.next
    print(f"   原链表: [1,2,3,4,5]")
    print(f"   反转后: {result_list}")
    
    # 测试3: 合并两个有序数组
    print("\n3. 合并两个有序数组:")
    nums1 = [1, 2, 3, 0, 0, 0]
    m, n = 3, 3
    nums2 = [2, 5, 6]
    print(f"   nums1={nums1[:m]}, m={m}")
    print(f"   nums2={nums2}, n={n}")
    merge(nums1, m, nums2, n)
    print(f"   合并后: {nums1}")
    
    # 测试4: 有效的括号
    print("\n4. 有效的括号:")
    test_cases = ["()", "()[]{}", "(]", "([)]", "{[]}"]
    for s in test_cases:
        print(f"   '{s}' -> {is_valid(s)}")
    
    # 测试5: 最大子数组和
    print("\n5. 最大子数组和:")
    nums = [-2, 1, -3, 4, -1, 2, 1, -5, 4]
    result = max_sub_array(nums)
    print(f"   nums={nums}")
    print(f"   最大子数组和: {result}")
    
    # 测试6: 爬楼梯
    print("\n6. 爬楼梯:")
    for n in [2, 3, 4, 5]:
        print(f"   n={n}: {climb_stairs(n)} 种方法")
    
    # 测试7: 二叉树的中序遍历
    print("\n7. 二叉树的中序遍历:")
    root = TreeNode(1)
    root.right = TreeNode(2)
    root.right.left = TreeNode(3)
    result = inorder_traversal(root)
    print(f"   树结构: 1 -> null, 2 -> 3")
    print(f"   中序遍历结果: {result}")
    
    # 测试8: 对称二叉树
    print("\n8. 对称二叉树:")
    root = TreeNode(1)
    root.left = TreeNode(2)
    root.right = TreeNode(2)
    root.left.left = TreeNode(3)
    root.left.right = TreeNode(4)
    root.right.left = TreeNode(4)
    root.right.right = TreeNode(3)
    print(f"   对称树 [1,2,2,3,4,4,3] -> {is_symmetric(root)}")
    
    # 测试9: 环形链表
    print("\n9. 环形链表:")
    # 创建带环链表: 1->2->3->4->2(环)
    node1 = ListNode(1)
    node2 = ListNode(2)
    node3 = ListNode(3)
    node4 = ListNode(4)
    node1.next = node2
    node2.next = node3
    node3.next = node4
    node4.next = node2  # 形成环
    print(f"   链表 1->2->3->4->2(环) 是否有环: {has_cycle(node1)}")
    
    # 测试10: 最长公共前缀
    print("\n10. 最长公共前缀:")
    strs = ["flower", "flow", "flight"]
    print(f"   strs={strs}")
    print(f"   最长公共前缀: '{longest_common_prefix(strs)}'")
    
    print("\n" + "=" * 50)
    print("所有测试完成!")
    print("=" * 50)


if __name__ == "__main__":
    test_all()
