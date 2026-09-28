/* SPDX-License-Identifier: MIT */
/* Public source-built active workload for the exact SPIKE Prime CPU map. */

.syntax unified
.cpu cortex-m4
.thumb

.equ USART2_DR,  0x40004404
.equ USART2_CR1, 0x4000440c

.section .isr_vector, "a", %progbits
.global vector_table
vector_table:
    .word 0x20050000
    .word reset + 1

.section .text, "ax", %progbits
.thumb_func
.global reset
reset:
    ldr r0, =USART2_CR1
    ldr r1, =0x2008       /* UE | TE */
    str r1, [r0]
    ldr r0, =USART2_DR
    movs r1, #'S'
    str r1, [r0]
    movs r1, #'P'
    str r1, [r0]
    movs r1, #'I'
    str r1, [r0]
    movs r1, #'K'
    str r1, [r0]
    movs r1, #'E'
    str r1, [r0]
    movs r1, #10
    str r1, [r0]

    movs r2, #0
    ldr r3, =0x13579bdf
1:
    adds r2, r2, #1
    eors r3, r3, r2
    subs r3, r3, #7
    cmp r2, #0
    bne 1b
    b 1b

