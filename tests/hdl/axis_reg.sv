`default_nettype none
// axis_reg: AXI-Stream skid buffer (full throughput, registered tready). Test DUT for
// tb-common only. CORRUPT_BEAT >= 0 flips tdata bit 0 of that beat index, so a test can
// prove the scoreboard catches a real datapath bug.
module axis_reg #(
    parameter int DATA_W       = 32,
    parameter int USER_W       = 4,
    parameter int CORRUPT_BEAT = -1
) (
    input  wire logic                clk,
    input  wire logic                rst,
    input  wire logic [DATA_W-1:0]   s_tdata_i,
    input  wire logic [DATA_W/8-1:0] s_tkeep_i,
    input  wire logic [USER_W-1:0]   s_tuser_i,
    input  wire logic                s_tlast_i,
    input  wire logic                s_tvalid_i,
    output logic                     s_tready_o,
    output logic [DATA_W-1:0]        m_tdata_o,
    output logic [DATA_W/8-1:0]      m_tkeep_o,
    output logic [USER_W-1:0]        m_tuser_o,
    output logic                     m_tlast_o,
    output logic                     m_tvalid_o,
    input  wire logic                m_tready_i
);
    localparam int W = DATA_W + DATA_W / 8 + USER_W + 1;

    logic [W-1:0] in_w, skid_q, out_q;
    logic         skid_valid_q;
    logic [31:0]  beat_cnt_q;

    always_comb begin
        in_w = {s_tdata_i, s_tkeep_i, s_tuser_i, s_tlast_i};
        if (CORRUPT_BEAT >= 0 && beat_cnt_q == 32'(CORRUPT_BEAT)) in_w[W-DATA_W] ^= 1'b1;
        {m_tdata_o, m_tkeep_o, m_tuser_o, m_tlast_o} = out_q;
        s_tready_o = !skid_valid_q;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            m_tvalid_o   <= 1'b0;
            skid_valid_q <= 1'b0;
            beat_cnt_q   <= '0;
        end else begin
            if (s_tvalid_i && s_tready_o) beat_cnt_q <= beat_cnt_q + 32'd1;
            if (!m_tvalid_o || m_tready_i) begin
                // Output register free: load from skid if occupied, else from input.
                if (skid_valid_q) begin
                    out_q        <= skid_q;
                    m_tvalid_o   <= 1'b1;
                    skid_valid_q <= 1'b0;
                end else begin
                    out_q      <= in_w;
                    m_tvalid_o <= s_tvalid_i;
                end
            end else if (s_tvalid_i && s_tready_o) begin
                skid_q       <= in_w;
                skid_valid_q <= 1'b1;
            end
        end
    end
endmodule
`default_nettype wire
