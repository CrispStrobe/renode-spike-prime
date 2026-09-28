/* SPDX-License-Identifier: MIT */
/*
 * Independently authored AM1808 MMC/SD0 CMD17 proof.
 * Build normally for PIO or define MMC_EDMA for the EDMA0 channel-16 path.
 * Register layout follows TI SPRUH82C chapter 26. No LEGO code is used.
 */

.syntax unified
.cpu arm926ej-s
.arm

.equ UART1_THR,          0x01d0c000
.equ PSC0,               0x01c10000
.equ PSC_PTCMD,          0x120
.equ PSC_PTSTAT,         0x128
.equ PSC_MDSTAT5,        0x814
.equ PSC_MDCTL5,         0xa14
.equ PSC_STATE_MASK,     0x1f
.equ PSC_ENABLE,         0x3
.equ MMC0,               0x01c40000
.equ MMC_ST0,            0x08
.equ MMC_IM,             0x10
.equ MMC_BLEN,           0x1c
.equ MMC_NBLK,           0x20
.equ MMC_NBLC,           0x24
.equ MMC_DRR,            0x28
.equ MMC_CMD,            0x30
.equ MMC_ARG,            0x34
.equ MMC_FIFOCTL,        0x74
.equ ST_DATDNE,          0x0001
.equ ST_RSPDNE,          0x0004
.equ ST_DRRDY,           0x0400
.equ ST_TRNDNE,          0x1000
.equ ST_REQUIRED,        ST_RSPDNE | ST_TRNDNE | ST_DATDNE
.equ CMD17_PIO,          0x00002291
.equ CMD17_EDMA,         0x00012291

.equ EDMA0_CC,           0x01c00000
.equ EDMA_DRAE0,         0x340
.equ EDMA_SHADOW,        0x01c02000
.equ EDMA_EESR,          0x30
.equ EDMA_IESR,          0x60
.equ EDMA_IPR,           0x68
.equ EDMA_ICR,           0x70
.equ EDMA_PARAM16,       0x01c04200
.equ EDMA_MASK16,        0x00010000
.equ EDMA_OPT,           0x00110205 /* TCINTEN, TCC16, FWID32, AB-sync, SAM */

.equ AINTC_GER,          0xfffee010
.equ AINTC_SICR,         0xfffee024
.equ AINTC_EISR,         0xfffee028
.equ AINTC_HIEISR,       0xfffee034
.equ AINTC_CMR2,         0xfffee408
.equ AINTC_CMR4,         0xfffee410
.equ AINTC_HIPIR2,       0xfffee904
.equ EDMA_COMPLETION,    11
.equ MMC0_EVENT,         16

.equ DESTINATION,        0x80001000
.equ PATTERN_BASE,       0xa5a50000

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
    msr cpsr_c, #0xd2
    ldr sp, =0xffff1f00
    msr cpsr_c, #0xd3
    ldr sp, =0xffff1e00
    mov r9, #0              /* EDMA build: bit0 MMC done, bit1 EDMA done */
    mov r10, #0             /* accumulated MMCST0 evidence */

    /* The public EV3 boot flow enables PSC0 module 5 before MMC0 access. */
    ldr r0, =PSC0
    ldr r1, [r0, #PSC_MDCTL5]
    bic r1, r1, #PSC_STATE_MASK
    orr r1, r1, #PSC_ENABLE
    str r1, [r0, #PSC_MDCTL5]
    mov r1, #1
    str r1, [r0, #PSC_PTCMD]
    ldr r1, [r0, #PSC_PTSTAT]
    tst r1, #1
    bne fail_power
    ldr r1, [r0, #PSC_MDSTAT5]
    and r1, r1, #PSC_STATE_MASK
    cmp r1, #PSC_ENABLE
    bne fail_power

    /* One 512-byte block and a 32-byte FIFO/DMA threshold. */
    ldr r0, =MMC0
    mov r1, #1
    str r1, [r0, #MMC_FIFOCTL]
    mov r1, #0
    str r1, [r0, #MMC_FIFOCTL]
    mov r1, #512
    str r1, [r0, #MMC_BLEN]
    mov r1, #1
    str r1, [r0, #MMC_NBLK]

.ifdef MMC_EDMA
    bl configure_edma
    bl configure_interrupts
    ldr r0, =MMC0
    ldr r1, =ST_REQUIRED
    str r1, [r0, #MMC_IM]
    mov r1, #0
    str r1, [r0, #MMC_ARG]
    ldr r1, =CMD17_EDMA
    str r1, [r0, #MMC_CMD]
    msr cpsr_c, #0x53

    ldr r8, =0x00800000
1:
    cmp r9, #3
    beq edma_validate
    subs r8, r8, #1
    bne 1b
    ldr r1, =failure_timeout_message
    b print
.else
    mov r1, #0
    str r1, [r0, #MMC_ARG]
    ldr r1, =CMD17_PIO
    str r1, [r0, #MMC_CMD]

    mov r6, #0              /* word index */
    ldr r7, =PATTERN_BASE
    ldr r8, =0x00800000
2:
    ldr r1, [r0, #MMC_ST0]
    orr r10, r10, r1
    tst r1, #ST_DRRDY
    beq 3f
    ldr r2, [r0, #MMC_DRR]
    add r3, r7, r6
    cmp r2, r3
    bne fail_data
    add r6, r6, #1
    cmp r6, #128
    beq pio_validate
3:
    subs r8, r8, #1
    bne 2b
    ldr r1, =failure_timeout_message
    b print
.endif

pio_validate:
    ldr r1, [r0, #MMC_ST0]
    orr r10, r10, r1
    ldr r1, [r0, #MMC_NBLC]
    cmp r1, #0
    bne fail_nblc
    ldr r2, =ST_REQUIRED
    and r1, r10, r2
    cmp r1, r2
    bne fail_status
    ldr r1, =success_pio_message
    b print

.ifdef MMC_EDMA
configure_edma:
    ldr r0, =DESTINATION
    ldr r1, =0xdeadbeef
    mov r2, #128
4:
    str r1, [r0], #4
    subs r2, r2, #1
    bne 4b

    ldr r0, =EDMA_PARAM16
    ldr r1, =EDMA_OPT
    str r1, [r0, #0x00]
    ldr r1, =MMC0 + MMC_DRR
    str r1, [r0, #0x04]
    ldr r1, =0x00080004    /* BCNT=8, ACNT=4 */
    str r1, [r0, #0x08]
    ldr r1, =DESTINATION
    str r1, [r0, #0x0c]
    ldr r1, =0x00040000    /* DSTBIDX=4, SRCBIDX=0 */
    str r1, [r0, #0x10]
    ldr r1, =0x0000ffff    /* no link */
    str r1, [r0, #0x14]
    ldr r1, =0x00200000    /* DSTCIDX=32, SRCCIDX=0 */
    str r1, [r0, #0x18]
    mov r1, #16
    str r1, [r0, #0x1c]

    ldr r0, =EDMA0_CC
    ldr r1, =EDMA_MASK16
    str r1, [r0, #EDMA_DRAE0]
    ldr r0, =EDMA_SHADOW
    str r1, [r0, #EDMA_IESR]
    str r1, [r0, #EDMA_EESR]
    bx lr

configure_interrupts:
    /* Events 11 and 16 route to IRQ host channel 1. */
    ldr r0, =AINTC_CMR2
    ldr r1, =0x01000000
    str r1, [r0]
    ldr r0, =AINTC_CMR4
    mov r1, #1
    str r1, [r0]
    ldr r0, =AINTC_EISR
    mov r1, #EDMA_COMPLETION
    str r1, [r0]
    mov r1, #MMC0_EVENT
    str r1, [r0]
    ldr r0, =AINTC_HIEISR
    mov r1, #1
    str r1, [r0]
    ldr r0, =AINTC_GER
    str r1, [r0]
    bx lr

edma_validate:
    ldr r0, =MMC0
    ldr r1, [r0, #MMC_ST0]
    orr r10, r10, r1
    ldr r1, [r0, #MMC_NBLC]
    cmp r1, #0
    bne fail_nblc
    ldr r2, =ST_REQUIRED
    and r1, r10, r2
    cmp r1, r2
    bne fail_status

    ldr r0, =DESTINATION
    ldr r7, =PATTERN_BASE
    mov r6, #0
5:
    ldr r1, [r0], #4
    add r2, r7, r6
    cmp r1, r2
    bne fail_data
    add r6, r6, #1
    cmp r6, #128
    bne 5b
    ldr r1, =success_edma_message
    b print
.endif

fail_data:
    ldr r1, =failure_data_message
    b print
fail_status:
    ldr r1, =failure_status_message
    b print
fail_nblc:
    ldr r1, =failure_nblc_message
    b print
fail_power:
    ldr r1, =failure_power_message

print:
    ldr r0, =UART1_THR
6:
    ldrb r2, [r1], #1
    cmp r2, #0
    beq 7f
    strb r2, [r0]
    b 6b
7:
    b 7b

irq:
.ifdef MMC_EDMA
    stmfd sp!, {r0-r3, lr}
    ldr r0, =AINTC_HIPIR2
    ldr r1, [r0]
    cmp r1, #EDMA_COMPLETION
    beq irq_edma
    cmp r1, #MMC0_EVENT
    beq irq_mmc
    ldr r1, =failure_irq_message
    b irq_failure

irq_edma:
    ldr r0, =EDMA_SHADOW
    ldr r1, [r0, #EDMA_IPR]
    ldr r2, =EDMA_MASK16
    tst r1, r2
    beq irq_bad
    str r2, [r0, #EDMA_ICR]
    orr r9, r9, #2
    mov r3, #EDMA_COMPLETION
    b irq_ack

irq_mmc:
    ldr r0, =MMC0
    ldr r1, [r0, #MMC_ST0]
    orr r10, r10, r1
    ldr r3, =(ST_TRNDNE | ST_DATDNE)
    and r2, r1, r3
    cmp r2, r3
    orreq r9, r9, #1
    mov r3, #MMC0_EVENT
    b irq_ack

irq_bad:
    ldr r1, =failure_irq_message
irq_failure:
    ldr r0, =UART1_THR
8:
    ldrb r2, [r1], #1
    cmp r2, #0
    strbne r2, [r0]
    bne 8b
    mov r9, #0xff
    mov r3, #EDMA_COMPLETION

irq_ack:
    ldr r0, =AINTC_SICR
    str r3, [r0]
    ldmfd sp!, {r0-r3, lr}
    subs pc, lr, #4
.else
    subs pc, lr, #4
.endif

success_pio_message:
    .asciz "EV3 MMC PIO READ OK\n"
success_edma_message:
    .asciz "EV3 MMC EDMA READ OK\n"
failure_data_message:
    .asciz "EV3 MMC FAIL DATA\n"
failure_status_message:
    .asciz "EV3 MMC FAIL STATUS\n"
failure_nblc_message:
    .asciz "EV3 MMC FAIL NBLC\n"
failure_power_message:
    .asciz "EV3 MMC FAIL POWER\n"
failure_timeout_message:
    .asciz "EV3 MMC FAIL TIMEOUT\n"
failure_irq_message:
    .asciz "EV3 MMC FAIL IRQ\n"
