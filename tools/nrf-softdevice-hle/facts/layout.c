#include <stddef.h>
#include "ble.h"
#include "ble_gap.h"
#include "ble_gatts.h"
#include "nrf_soc.h"
#include "nrf_sdm.h"
#define O(T, f) { #T "." #f, offsetof(T, f), sizeof(((T*)0)->f) },
#define S(T) { #T, 0xFFFF, sizeof(T) },
struct e { const char *n; unsigned short off; unsigned short size; };
const struct e layout[] = {
 S(ble_evt_t) O(ble_evt_t, header) O(ble_evt_t, evt)
 S(ble_evt_hdr_t) O(ble_evt_hdr_t, evt_id) O(ble_evt_hdr_t, evt_len)
 S(ble_gap_evt_t) O(ble_gap_evt_t, conn_handle) O(ble_gap_evt_t, params)
 S(ble_gap_addr_t) O(ble_gap_addr_t, addr_type) O(ble_gap_addr_t, addr)
 S(ble_gap_conn_params_t) O(ble_gap_conn_params_t, min_conn_interval) O(ble_gap_conn_params_t, max_conn_interval) O(ble_gap_conn_params_t, slave_latency) O(ble_gap_conn_params_t, conn_sup_timeout)
 S(ble_gap_evt_connected_t) O(ble_gap_evt_connected_t, peer_addr) O(ble_gap_evt_connected_t, own_addr) O(ble_gap_evt_connected_t, conn_params)
 S(ble_gap_evt_disconnected_t) O(ble_gap_evt_disconnected_t, reason)
 S(ble_gap_evt_sec_params_request_t) S(ble_gap_sec_params_t)
 S(ble_gap_evt_auth_status_t) S(ble_gap_evt_conn_sec_update_t) S(ble_gap_evt_timeout_t)
 S(ble_gatts_evt_t) O(ble_gatts_evt_t, conn_handle) O(ble_gatts_evt_t, params)
 S(ble_gatts_evt_write_t) O(ble_gatts_evt_write_t, handle) O(ble_gatts_evt_write_t, op) O(ble_gatts_evt_write_t, context) O(ble_gatts_evt_write_t, offset) O(ble_gatts_evt_write_t, len) O(ble_gatts_evt_write_t, data)
 S(ble_gatts_attr_context_t) O(ble_gatts_attr_context_t, srvc_uuid) O(ble_gatts_attr_context_t, char_uuid) O(ble_gatts_attr_context_t, desc_uuid) O(ble_gatts_attr_context_t, srvc_handle) O(ble_gatts_attr_context_t, value_handle) O(ble_gatts_attr_context_t, type)
 S(ble_gatts_evt_sys_attr_missing_t) O(ble_gatts_evt_sys_attr_missing_t, hint)
 S(ble_gatts_evt_hvc_t)
 S(ble_gatts_evt_rw_authorize_request_t) O(ble_gatts_evt_rw_authorize_request_t, type) O(ble_gatts_evt_rw_authorize_request_t, request)
 S(ble_gatts_evt_read_t) O(ble_gatts_evt_read_t, handle) O(ble_gatts_evt_read_t, context) O(ble_gatts_evt_read_t, offset)
 S(ble_common_evt_t) O(ble_common_evt_t, conn_handle) O(ble_common_evt_t, params)
 S(ble_evt_tx_complete_t) O(ble_evt_tx_complete_t, count)
 S(ble_uuid_t) O(ble_uuid_t, uuid) O(ble_uuid_t, type)
 S(ble_uuid128_t)
 S(ble_gatts_char_md_t) O(ble_gatts_char_md_t, char_props) O(ble_gatts_char_md_t, char_ext_props) O(ble_gatts_char_md_t, p_char_user_desc) O(ble_gatts_char_md_t, char_user_desc_max_size) O(ble_gatts_char_md_t, char_user_desc_size) O(ble_gatts_char_md_t, p_char_pf) O(ble_gatts_char_md_t, p_user_desc_md) O(ble_gatts_char_md_t, p_cccd_md) O(ble_gatts_char_md_t, p_sccd_md)
 S(ble_gatts_attr_t) O(ble_gatts_attr_t, p_uuid) O(ble_gatts_attr_t, p_attr_md) O(ble_gatts_attr_t, init_len) O(ble_gatts_attr_t, init_offs) O(ble_gatts_attr_t, max_len) O(ble_gatts_attr_t, p_value)
 S(ble_gatts_attr_md_t) O(ble_gatts_attr_md_t, read_perm) O(ble_gatts_attr_md_t, write_perm)
 S(ble_gatts_char_handles_t) O(ble_gatts_char_handles_t, value_handle) O(ble_gatts_char_handles_t, user_desc_handle) O(ble_gatts_char_handles_t, cccd_handle) O(ble_gatts_char_handles_t, sccd_handle)
 S(ble_gatts_hvx_params_t) O(ble_gatts_hvx_params_t, handle) O(ble_gatts_hvx_params_t, type) O(ble_gatts_hvx_params_t, offset) O(ble_gatts_hvx_params_t, p_len) O(ble_gatts_hvx_params_t, p_data)
 S(ble_gatts_value_t) O(ble_gatts_value_t, len) O(ble_gatts_value_t, offset) O(ble_gatts_value_t, p_value)
 S(ble_gap_adv_params_t) O(ble_gap_adv_params_t, type) O(ble_gap_adv_params_t, p_peer_addr) O(ble_gap_adv_params_t, fp) O(ble_gap_adv_params_t, p_whitelist) O(ble_gap_adv_params_t, interval) O(ble_gap_adv_params_t, timeout)
 S(ble_gap_conn_sec_mode_t)
 S(ble_enable_params_t)
 S(ble_gatts_rw_authorize_reply_params_t)
 S(ble_gap_whitelist_t)
 S(ble_version_t)
 S(nrf_clock_lfclksrc_t)
};
const unsigned layout_count = sizeof(layout)/sizeof(layout[0]);
