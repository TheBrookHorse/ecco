from typing import List, TextIO

from ..ecco import ARGS
from ..parsing import ASTNode
from ..scanning import TokenType
from ..utils import EccoFatalException, EccoFileError, LogLevel, log
from .llvmstackentry import LLVMStackEntry
from .llvmvalue import LLVMValue, LLVMValueType

LLVM_OUT_FILE: TextIO
LLVM_VIRTUAL_REGISTER_NUMBER: int
LLVM_FREE_REGISTER_COUNT: int
LLVM_LOADED_REGISTERS: List[LLVMValue]


def translate_init():
    global LLVM_OUT_FILE, LLVM_VIRTUAL_REGISTER_NUMBER, LLVM_FREE_REGISTER_COUNT, LLVM_LOADED_REGISTERS

    try:
        LLVM_OUT_FILE = open(ARGS.output, "w")
    except Exception as e:
        raise EccoFileError(str(e))

    LLVM_VIRTUAL_REGISTER_NUMBER = 0

    LLVM_FREE_REGISTER_COUNT = 0

    LLVM_LOADED_REGISTERS = []


def get_next_local_virtual_register() -> int:
    global LLVM_VIRTUAL_REGISTER_NUMBER
    LLVM_VIRTUAL_REGISTER_NUMBER += 1
    return LLVM_VIRTUAL_REGISTER_NUMBER


def update_free_register_count(delta: int) -> int:
    global LLVM_FREE_REGISTER_COUNT
    LLVM_FREE_REGISTER_COUNT += delta
    return LLVM_FREE_REGISTER_COUNT - delta


def get_free_register_count() -> int:
    global LLVM_FREE_REGISTER_COUNT
    return LLVM_FREE_REGISTER_COUNT


def determine_binary_expression_stack_allocation(root: ASTNode) -> List[LLVMStackEntry]:
    from .llvm import get_next_local_virtual_register

    left_entry: List[LLVMStackEntry]
    right_entry: List[LLVMStackEntry]

    if root.left or root.right:
        if root.left:
            left_entry = determine_binary_expression_stack_allocation(root.left)
        if root.right:
            right_entry = determine_binary_expression_stack_allocation(root.right)

        return left_entry + right_entry
    else:
        out_entry = LLVMStackEntry(
            LLVMValue(
                LLVMValueType.VIRTUAL_REGISTER,
                get_next_local_virtual_register(),
            ),
            4,
        )
        update_free_register_count(1)
        return [out_entry]


def ast_to_llvm(root: ASTNode) -> LLVMValue:
    from .llvm import (
        llvm_binary_arithmetic,
        llvm_ensure_registers_loaded,
        llvm_store_constant,
    )

    left_vr: LLVMValue
    right_vr: LLVMValue

    if root.left:
        left_vr = ast_to_llvm(root.left)
    if root.right:
        right_vr = ast_to_llvm(root.right)
    
    if root.token.is_binary_arithmetic():
        left_vr, right_vr = llvm_ensure_registers_loaded([left_vr, right_vr])
        return llvm_binary_arithmetic(root.token, left_vr, right_vr)
    elif root.token.is_terminal():
        if root.token.type == TokenType.INTEGER_LITERAL:
            return llvm_store_constant(root.token.value)
    else:
        raise EccoFatalException(
            "", f'Unknown token encountered in ast_to_llvm: "{str(root.token)}"'
        )

    return LLVMValue(LLVMValueType.NONE, None)


def generate_llvm(root: ASTNode):
    global LLVM_OUT_FILE

    translate_init()

    from .llvm import (
        llvm_postamble,
        llvm_preamble,
        llvm_print_int,
        llvm_stack_allocation,
    )

    llvm_preamble()

    llvm_stack_allocation(determine_binary_expression_stack_allocation(root))

    print_vr: LLVMValue = ast_to_llvm(root)

    llvm_print_int(print_vr)

    llvm_postamble()

    if not LLVM_OUT_FILE.closed:
        LLVM_OUT_FILE.close()

    log(LogLevel.DEBUG, f"LLVM written to {LLVM_OUT_FILE.name}")