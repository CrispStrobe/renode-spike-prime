/* SPDX-License-Identifier: MIT */
/* Idle workload for the exact SPIKE Prime CPU map: SysTick at 1 kHz wakes a
 * WFI loop, as an RTOS idle thread does. Used by the lockstep timing probe. */

.syntax unified
.cpu cortex-m4
.thumb

.equ SYST_CSR, 0xe000e010
.equ SYST_RVR, 0xe000e014
.equ SYST_CVR, 0xe000e018

.section .isr_vector, "a", %progbits
.global vector_table
vector_table:
    .word 0x20050000
    .word reset + 1
    .rept 13
    .word default_handler + 1
    .endr
    .word systick + 1

.section .text, "ax", %progbits
.thumb_func
.global reset
reset:
    ldr r0, =SYST_RVR
    ldr r1, =95999        /* 96 MHz core clock: 1 ms */
    str r1, [r0]
    ldr r0, =SYST_CVR
    movs r1, #0
    str r1, [r0]
    ldr r0, =SYST_CSR
    movs r1, #7           /* ENABLE | TICKINT | CLKSOURCE */
    str r1, [r0]
    movs r4, #0
1:
    wfi
    b 1b

.thumb_func
systick:
    adds r4, r4, #1
    bx lr

.thumb_func
default_handler:
    b default_handler
