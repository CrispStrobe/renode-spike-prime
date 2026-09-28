/* SPDX-License-Identifier: MIT */
/* Source-built public smoke image. It contains no LEGO firmware material. */

.syntax unified
.cpu arm926ej-s
.arm

.equ UART1_THR,  0x01d0c000
.equ AINTC_GER,  0xfffee010
.equ AINTC_SISR, 0xfffee020
.equ AINTC_SICR, 0xfffee024
.equ AINTC_EISR, 0xfffee028
.equ AINTC_HIEISR, 0xfffee034
.equ AINTC_CMR13, 0xfffee434

.section .vectors, "ax"
.global _start
_start:
    b reset
    b .
    b .
    b .
    b .
    b .
    b irq
    b .

reset:
    msr cpsr_c, #0xd2       /* IRQ mode, masked */
    ldr sp, =0x8001f000
    msr cpsr_c, #0xd3       /* SVC mode, masked */
    ldr sp, =0x8001e000

    ldr r0, =UART1_THR
    mov r1, #'E'
    strb r1, [r0]
    mov r1, #'V'
    strb r1, [r0]
    mov r1, #'3'
    strb r1, [r0]
    mov r1, #' '
    strb r1, [r0]
    mov r1, #'A'
    strb r1, [r0]
    mov r1, #'R'
    strb r1, [r0]
    mov r1, #'M'
    strb r1, [r0]
    mov r1, #'9'
    strb r1, [r0]
    mov r1, #' '
    strb r1, [r0]

    /* system event 53 (UART1) is in CMR13 byte 1; route to IRQ host 1. */
    ldr r0, =AINTC_CMR13
    mov r1, #0x100
    str r1, [r0]
    ldr r0, =AINTC_EISR
    mov r1, #53
    str r1, [r0]
    ldr r0, =AINTC_HIEISR
    mov r1, #1
    str r1, [r0]
    ldr r0, =AINTC_GER
    str r1, [r0]
    msr cpsr_c, #0x53       /* SVC mode, IRQ enabled */

    /* Deterministically exercise AINTC without relying on a fake timer. */
    ldr r0, =AINTC_SISR
    mov r1, #53
    str r1, [r0]
1:  b 1b

irq:
    stmfd sp!, {r0-r1, lr}
    ldr r0, =AINTC_SICR
    mov r1, #53
    str r1, [r0]
    ldr r0, =UART1_THR
    mov r1, #'I'
    strb r1, [r0]
    mov r1, #'R'
    strb r1, [r0]
    mov r1, #'Q'
    strb r1, [r0]
    mov r1, #10
    strb r1, [r0]
    ldmfd sp!, {r0-r1, lr}
    subs pc, lr, #4
