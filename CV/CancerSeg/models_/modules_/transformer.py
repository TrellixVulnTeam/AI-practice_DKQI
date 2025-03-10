from models_.modules_.tf_submod import *
from utils import subsequent_mask


class EncoderDecoder(nn.Module):
    """
    A standard Encoder-Decoder architecture. Base for this and many other models.
    """

    def __init__(self, encoder, decoder, src_embed, tgt_embed, generator):
        super(EncoderDecoder, self).__init__()
        self.encoder = encoder
        self.decoder = decoder
        self.src_embed = src_embed
        self.tgt_embed = tgt_embed
        self.generator = generator

    def forward(self, src, tgt, src_mask, tgt_mask):
        "Take in and process masked src and target sequences."
        return self.decode(self.encode(src, src_mask), src_mask,
                           tgt, tgt_mask)

    def encode(self, src, src_mask):
        return self.encoder(self.src_embed(src), src_mask)

    def decode(self, memory, src_mask, tgt, tgt_mask):
        return self.decoder(self.tgt_embed(tgt), memory, src_mask, tgt_mask)


class Encoder(nn.Module):
    "Core encoder is a stack of N layers"

    def __init__(self, layer, N):
        super(Encoder, self).__init__()
        self.layers = clones(layer, N)
        self.norm = LayerNorm(layer.size)

    def forward(self, x, mask, mem=None):
        "Pass the input (and mask) through each layer in turn."
        # if mem is not None:
        #     mem = torch.cat([mem, x], dim=1)  # 这样upper layer还在attn原来的x
        for layer in self.layers:
            if mem is None:
                x = layer(x, mask) #+ x
            else:
                x, mem, attn = layer(x, mask, mem)
        return x if mem is None else (x, mem, attn)
        # return x  # if memory is None else self.norm(x)  # baseline 多层时，没有norm在grid上收敛更快
        # return self.norm(x)


class EncoderLayer(nn.Module):
    "Encoder is made up of self-attn and feed forward (defined below)"

    def __init__(self, size, self_attn, feed_forward, dropout):
        super(EncoderLayer, self).__init__()
        self.self_attn = self_attn
        self.feed_forward = feed_forward
        self.sublayer = clones(SublayerConnection(size, dropout), N=3)
        self.size = size

    def forward(self, x, mask, mem=None):
        "Follow Figure 1 (left) for connections."
        if mem is None:
            x = self.sublayer[0](x, lambda x: self.self_attn(x, x, x, mask))
        else:
            mem_ = torch.cat([mem, x], dim=1)  # stack时，x每次都变，但mem没变
            # # x = self.sublayer[0](x, lambda x: self.self_attn(x, x, x, mask))
            # self.mem_size = 30
            # out = torch.zeros(x.size()).to(x.device)
            # C = self.chunk = 10
            # # x = self.pos_encoder(x)
            # x_ = x[:, 0: C]
            # out[:, 0: C] = self.sublayer[0](x_, lambda x_: self.self_attn(x_, x_, x_, mask[:, 0: C]))
            #
            # mem = x[:, 0: C].detach()  # tf_enc[:, 0: C].detach()
            # # mem = tf_enc[:, 0: C].detach().mean(1, keepdim=True)
            # # mem = self.conv_v_mem(tf_enc[:, 0: C].detach().permute(0, 2, 1)).permute(0, 2, 1)
            # for i in range(1, (x.size(1) - 1) // C + 1):
            #     x_ = x[:, i * C:(i + 1) * C]
            #     m = torch.cat([mem, x_], dim=1)  # stack时，x每次都变，但mem没变
            #     out[:, i * C:(i + 1) * C]  = self.sublayer[0](x_, lambda x_: self.self_attn(x_, m, m, mask[:, i * C:(i + 1) * C]))
            #
            #     new_m = x[:, i * C:(i + 1) * C].detach()  # tf_enc[:, i * C:(i + 1) * C].detach()
            #     # new_m = tf_enc[:, i * C:(i + 1) * C].detach().mean(1, keepdim=True)
            #     # # new_m = self.conv_v_mem(tf_enc[:, i * C:(i + 1) * C].detach().permute(0, 2, 1)).permute(0, 2, 1)
            #     mem = torch.cat([mem, new_m], dim=1)[:, max(0, mem.size(1) - self.mem_size):]
            x, mem_, attn = self.sublayer[0](x, lambda x: self.self_attn(x, mem, mem, mask, with_mem=True), with_mem=True)
            attn = attn.mean(2).mean(1)[:, :mem.size(1)]
            mem = mem[:, :mem.size(1)]
            # x, mem = self.sublayer[2](x, lambda x: self.self_attn(x, mem, mem, mask, with_mem=True), with_mem=True)

        x = self.sublayer[1](x, self.feed_forward)
        return x if mem is None else (x, mem, attn)


class Decoder(nn.Module):
    "Generic N layer decoder with masking."

    def __init__(self, layer, N):
        super(Decoder, self).__init__()
        self.layers = clones(layer, N)
        self.norm = LayerNorm(layer.size)

    def forward(self, x, memory, src_mask, tgt_mask):
        for layer in self.layers:
            x = layer(x, memory, src_mask, tgt_mask)

        return self.norm(x)


class DecoderLayer(nn.Module):
    "Decoder is made of self-attn, src-attn, and feed forward (defined below)"

    def __init__(self, size, self_attn, src_attn, feed_forward, dropout):
        super(DecoderLayer, self).__init__()
        self.size = size
        self.self_attn = self_attn
        self.src_attn = src_attn
        self.feed_forward = feed_forward
        self.sublayer = clones(SublayerConnection(size, dropout), 3)

    def forward(self, x, memory, src_mask, tgt_mask):
        "Follow Figure 1 (right) for connections."
        m = memory
        # print(x[0,:2,0])
        x = self.sublayer[0](x, lambda x: self.self_attn(x, x, x, tgt_mask))
        x = self.sublayer[1](x, lambda x: self.src_attn(x, m, m, src_mask))
        x = self.sublayer[2](x, self.feed_forward)
        return x


def make_transformer_encoder(N_layer=4, d_model=256, d_ff=1024, heads=8, dropout=0.1, ffn_layer='conv_relu_conv', first_kernel_size=9):
    "Helper: Construct a transformer encoder from hyperparameters."
    c = copy.deepcopy
    attn = MultiHeadedAttention(heads, d_model)
    if ffn_layer == 'conv_relu_conv':
        ff = ConvReluConvFFN(d_model, d_ff, first_kernel_size, second_kernel_size=1, dropout=dropout)
    else:
        ff = PositionwiseFeedForward(d_model, d_ff, dropout)
    model = Encoder(EncoderLayer(d_model, c(attn), c(ff), dropout), N_layer)
    # Initialize parameters with Glorot / fan_avg.
    for p in model.parameters():
        if p.dim() > 1:
            # nn.init.xavier_uniform(p)
            nn.init.xavier_uniform_(p)
    return model


def make_transformer_decoder(N_layer=4, d_model=256, d_ff=1024, heads=8, dropout=0.1, ffn_layer='conv_relu_conv', first_kernel_size=1):
    "Helper: Construct a transformer decoder from hyperparameters."
    c = copy.deepcopy
    attn = MultiHeadedAttention(heads, d_model)
    if ffn_layer == 'conv_relu_conv':
        ff = ConvReluConvFFN(d_model, d_ff, first_kernel_size, second_kernel_size=1, dropout=dropout)
    else:
        ff = PositionwiseFeedForward(d_model, d_ff, dropout)
    model = Decoder(DecoderLayer(d_model, c(attn), c(attn),
                                 c(ff), dropout), N_layer)
    # Initialize parameters with Glorot / fan_avg.
    for p in model.parameters():
        if p.dim() > 1:
            # nn.init.xavier_uniform(p)
            nn.init.xavier_uniform_(p)
    return model


def make_model(src_vocab, tgt_vocab, N=6, d_model=512, d_ff=2048, h=8, dropout=0.1):
    "Helper: Construct a model from hyperparameters."
    c = copy.deepcopy
    attn = MultiHeadedAttention(h, d_model)
    ff = PositionwiseFeedForward(d_model, d_ff, dropout)
    position = PositionalEncoding(d_model, dropout)
    model = EncoderDecoder(
        Encoder(EncoderLayer(d_model, c(attn), c(ff), dropout), N),
        Decoder(DecoderLayer(d_model, c(attn), c(attn),
                             c(ff), dropout), N),
        nn.Sequential(Embeddings(d_model, src_vocab), c(position)),
        nn.Sequential(Embeddings(d_model, tgt_vocab), c(position)),
        Generator(d_model, tgt_vocab))

    # This was important from their code.
    # Initialize parameters with Glorot / fan_avg.
    for p in model.parameters():
        if p.dim() > 1:
            # nn.init.xavier_uniform(p)
            nn.init.xavier_uniform_(p)
    return model


if __name__ == '__main__':
    encoder = make_transformer_encoder()
    x = torch.randn(24, 75, 256)
    x_mask = torch.randint(0, 2, (24, 75)) == 1
    hidden = encoder.forward(x, None)
    print(hidden.shape)
    decoder = make_transformer_decoder()
    y = decoder.forward(x, hidden, x_mask.unsqueeze(-2), x_mask.unsqueeze(-2))
    print(y.shape)
    sz = 5
    print(subsequent_mask(sz))
    # mask = (torch.triu(torch.ones(sz, sz)) == 1).transpose(0, 1)
    # print(mask)
    # x_mask = torch.randint(0, 2, (3, 5))==1
    # print(x_mask)
    # mask = x_mask.unsqueeze(-2) & subsequent_mask(x_mask.size(-1))
    # print(mask)
