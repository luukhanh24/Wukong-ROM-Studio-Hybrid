.class public final Lcom/wukong/manager/WukongPackageManagerHook;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field public static final e:Ljava/lang/String;

.field public static final f:Ljava/lang/String;

.field public static final g:[Ljava/lang/String;

.field public static final h:[Ljava/lang/String;

.field public static final i:Ljava/lang/reflect/Method;


# direct methods
.method static constructor <clinit>()V
    .registers 20

    const/16 v0, 0x14

    .line 8
    new-array v0, v0, [I

    fill-array-data v0, :array_14e

    const v1, 0x2e240446

    invoke-static {v0, v1}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/WukongPackageManagerHook;->e:Ljava/lang/String;

    const/16 v0, 0x1e

    .line 9
    new-array v0, v0, [I

    fill-array-data v0, :array_17a

    const v1, 0x4e3e7aeb  # 7.9893165E8f

    invoke-static {v0, v1}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/WukongPackageManagerHook;->f:Ljava/lang/String;

    const/16 v0, 0x2c

    .line 10
    new-array v1, v0, [I

    fill-array-data v1, :array_1ba

    const v2, 0x3c6e084

    .line 11
    invoke-static {v1, v2}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v1

    new-array v0, v0, [I

    fill-array-data v0, :array_216

    const v2, 0x6c5f3bd7

    .line 12
    invoke-static {v0, v2}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v0

    filled-new-array {v1, v0}, [Ljava/lang/String;

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/WukongPackageManagerHook;->g:[Ljava/lang/String;

    const/16 v0, 0xd

    .line 14
    new-array v1, v0, [J

    fill-array-data v1, :array_272

    const v2, 0x46576fa7

    const/16 v3, 0x31

    .line 15
    invoke-static {v1, v2, v3}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v4

    new-array v0, v0, [J

    fill-array-data v0, :array_2aa

    const v1, 0x67afd132

    .line 16
    invoke-static {v0, v1, v3}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v5

    const/16 v0, 0xf

    new-array v0, v0, [J

    fill-array-data v0, :array_2e2

    const v1, 0x35af7337

    const/16 v2, 0x39

    .line 17
    invoke-static {v0, v1, v2}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v6

    new-array v0, v3, [I

    fill-array-data v0, :array_322

    const v1, 0x58dd12f0

    .line 18
    invoke-static {v0, v1}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v7

    const/16 v0, 0x38

    new-array v1, v0, [I

    fill-array-data v1, :array_388

    const v2, 0x6343653b

    .line 19
    invoke-static {v1, v2}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v8

    const/16 v1, 0x30

    new-array v2, v1, [I

    fill-array-data v2, :array_3fc

    const v3, 0x4555205d

    .line 20
    invoke-static {v2, v3}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v9

    const/16 v2, 0xe

    new-array v3, v2, [J

    fill-array-data v3, :array_460

    const v10, 0x100812b2

    .line 21
    invoke-static {v3, v10, v0}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v10

    const/16 v3, 0xc

    new-array v11, v3, [J

    fill-array-data v11, :array_49c

    const v12, 0x63c436ba

    .line 22
    invoke-static {v11, v12, v1}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v11

    new-array v12, v0, [I

    fill-array-data v12, :array_4d0

    const v13, 0x6afbc1e1

    .line 23
    invoke-static {v12, v13}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v12

    new-array v13, v3, [J

    fill-array-data v13, :array_544

    const v14, 0x3d15b515

    .line 24
    invoke-static {v13, v14, v1}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v13

    new-array v14, v0, [I

    fill-array-data v14, :array_578

    const v15, 0x4b26996f  # 1.0918255E7f

    .line 25
    invoke-static {v14, v15}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v14

    new-array v15, v3, [J

    fill-array-data v15, :array_5ec

    const v3, 0x79ec56a0

    .line 26
    invoke-static {v15, v3, v1}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v15

    new-array v3, v2, [J

    fill-array-data v3, :array_620

    const v2, 0x12c47f28

    .line 27
    invoke-static {v3, v2, v0}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v2

    const/16 v3, 0xc

    new-array v3, v3, [J

    fill-array-data v3, :array_65c

    const v0, 0x5e286f4f

    .line 28
    invoke-static {v3, v0, v1}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v0

    const/16 v3, 0xe

    new-array v3, v3, [J

    fill-array-data v3, :array_690

    move-object/from16 v17, v0

    const v0, 0x16453b07

    move-object/from16 v18, v2

    const/16 v2, 0x38

    .line 29
    invoke-static {v3, v0, v2}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v0

    new-array v1, v1, [I

    fill-array-data v1, :array_6cc

    const v2, 0x7ba09f4c

    .line 30
    invoke-static {v1, v2}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v19

    move-object/from16 v16, v18

    move-object/from16 v18, v0

    filled-new-array/range {v4 .. v19}, [Ljava/lang/String;

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/WukongPackageManagerHook;->h:[Ljava/lang/String;

    const/4 v0, 0x7

    const/4 v1, 0x0

    .line 63
    :try_start_126
    new-array v0, v0, [J

    fill-array-data v0, :array_730

    const v2, 0x76cfedff

    const/16 v3, 0x1a

    invoke-static {v0, v2, v3}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v0

    invoke-static {v0}, Ljava/lang/Class;->forName(Ljava/lang/String;)Ljava/lang/Class;

    move-result-object v0

    const/16 v2, 0x12

    new-array v2, v2, [I

    fill-array-data v2, :array_750

    const v3, 0x7fbe0e60

    invoke-static {v2, v3}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v0, v2, v1}, Ljava/lang/Class;->getMethod(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;

    move-result-object v1
    :try_end_14a
    .catchall {:try_start_126 .. :try_end_14a} :catchall_14a

    .line 32
    :catchall_14a
    sput-object v1, Lcom/wukong/manager/WukongPackageManagerHook;->i:Ljava/lang/reflect/Method;

    return-void

    nop

    :array_14e
    .array-data 4
        0x446f71f
        0x457c0c9
        0x468c231
        0x479b3a8
        0x48afd7f
        0x49bbf58
        0x4aca852
        0x4bd15ea
        0x4cea782
        0x4df53e1
        0x4f09d79
        0x501adf2
        0x512ba63
        0x523dddf
        0x5343e94
        0x54520dd
        0x5568acb
        0x56776d2
        0x578b094
        0x5892abc
    .end array-data

    :array_17a
    .array-data 4
        0x7cd80439
        0x7cc79cbd
        0x7cb69122
        0x7ca50920
        0x7c940dc2
        0x7c83ae30
        0x7c72d7e4
        0x7c611a9c
        0x7c50c8fb
        0x7c3f8001
        0x7c2e1175
        0x7c1ddb48
        0x7c0ccd70
        0x7bfb7b41
        0x7bea4ce0
        0x7bd9f2b4
        0x7bc8473e
        0x7bb723ca
        0x7ba6526b
        0x7b953942
        0x7b848526
        0x7b736323
        0x7b62f7c9
        0x7b51abf3
        0x7b40f5a3
        0x7b2ffcbc
        0x7b1eb6eb
        0x7b0d510d
        0x7afcdd6b
        0x7aebe096
    .end array-data

    :array_1ba
    .array-data 4
        -0x1f7b7e74
        -0x1f6ac330
        -0x1f59427c
        -0x1f48d9f5
        -0x1f37dda7
        -0x1f260ae3
        -0x1f154dec
        -0x1f040656
        -0x1ef3c303
        -0x1ee2719c
        -0x1ed17535
        -0x1ec0e2c4
        -0x1eaf6312
        -0x1e9e22b4
        -0x1e8defa3
        -0x1e7c3dc9
        -0x1e6b2cbd
        -0x1e5a680a
        -0x1e49cf6d
        -0x1e387122
        -0x1e272986  # -4.9999392E20f
        -0x1e169cd2
        -0x1e05c83f
        -0x1df45feb
        -0x1de35cda
        -0x1dd21a0f
        -0x1dc1ecd9
        -0x1db0ef74
        -0x1d9f086d
        -0x1d8e78a3
        -0x1d7dc465
        -0x1d6c1825
        -0x1d5b8671
        -0x1d4a2229
        -0x1d39a4fe
        -0x1d286ee8
        -0x1d1742ec
        -0x1d06d8d7
        -0x1cf52e0d
        -0x1ce4aea4
        -0x1cd39089
        -0x1cc2a704
        -0x1cb103ef
        -0x1ca00909
    .end array-data

    :array_216
    .array-data 4
        0x3eb21061
        0x3ea118d7
        0x3e90ec1d
        0x3e7ff3a5
        0x3e6e7c46
        0x3e5d471b
        0x3e4cb0be
        0x3e3b78a2
        0x3e2a5b88
        0x3e191fdd
        0x3e0806bd
        0x3df71eca
        0x3de68142
        0x3dd53cab
        0x3dc4e21f
        0x3db3a3b9
        0x3da203f1
        0x3d91b43e
        0x3d805313
        0x3d6fa215
        0x3d5ea3c0
        0x3d4dbdd3
        0x3d3c83f8
        0x3d2b7ee4
        0x3d1a05a4
        0x3d09ad95
        0x3cf8c5a3
        0x3ce7debd
        0x3cd6207d
        0x3cc57f2b
        0x3cb4660e
        0x3ca34089
        0x3c92c783
        0x3c81c7f9
        0x3c70d50f
        0x3c5ff99d
        0x3c4e22e7
        0x3c3d04ff
        0x3c2c0bb3
        0x3c1bf242
        0x3c0a3726  # 0.008436f
        0x3bf90181
        0x3be88294
        0x3bd73d80
    .end array-data

    :array_272
    .array-data 8
        0x526a36899e99L
        0x4b1d6cfea6bcL
        0x36a92303c855L
        0x656ab132a7d3L
        0x2a93e287777dL
        0x23fb2e46cb4aL
        0x51b60dd8569bL
        0x1b1b91b700d3L
        0x1c0ae42564c7L
        0x28bc89a38feeL
        0x4a52ad0b3492L
        0x37cac57d7a0aL
        0x77bc000000caL
    .end array-data

    :array_2aa
    .array-data 8
        0x68ad3a2877bcL
        0x2c5d0c4e44c6L
        0x6e11e5c35a58L
        0x5c1be1ee54e5L
        0x62a64112ff94L
        0x2aea8a33467eL
        0x5cb4ee8f7cc6L
        0x32aa9631eec1L
        0x743d922417c5L
        0x417189e17d4cL
        0x7f69fd8b79edL
        0x55491f3ca98bL
        0x302400000099L
    .end array-data

    :array_2e2
    .array-data 8
        0x1da82bd48a8aL
        0x230f965582ecL
        0x78c75a285ba2L
        0x320314233df4L
        0x45e29914696L
        0x17b37c3bfebdL
        0x390230386800L
        0x2a88be637855L
        0x151799b68749L
        0xf1272c22e43L  # 8.1876110001886E-311
        0x4e388f7657e7L
        0x48ae794f5633L
        0x48107ff0c3eeL
        0x426668654e2fL
        0x332600000044L
    .end array-data

    :array_322
    .array-data 4
        0x12f03b58
        0x1301718c
        0x131266f0
        0x1323a7f6
        0x1334a680
        0x134584f0
        0x1356c6c8
        0x13674bfe
        0x1378ea03
        0x138931d9
        0x139a8420
        0x13ab48b9
        0x13bc561a
        0x13cd9d37
        0x13de434c
        0x13efca7a
        0x140094d3
        0x14111688
        0x14224e99
        0x14337e8b
        0x14448bd8
        0x1455c638
        0x1466523f
        0x14775f4f
        0x14880426
        0x1499b163
        0x14aa99a8
        0x14bb2935
        0x14ccc381
        0x14dd2997
        0x14eedfe2
        0x14ff8293  # 2.5799922E-26f
        0x1510d0a7
        0x1521e9c4
        0x15326ffc
        0x1543ed13
        0x155406c2
        0x1565fada
        0x1576940d
        0x1587c033
        0x15982a9b
        0x15a91a25
        0x15ba1eba
        0x15cbfdf9
        0x15dcec8d
        0x15ed0ee3
        0x15fed3ca
        0x160f80dc
        0x1620592d
    .end array-data

    :array_388
    .array-data 4
        0x68e26e0e
        0x68d1186e
        0x68c0343a
        0x68af88c0
        0x689e744f
        0x688d2071
        0x687c07f4
        0x686ba304
        0x685af3c3
        0x6849e97b
        0x68389e2e
        0x682786df
        0x6816c1f1
        0x680550ba
        0x67f40384
        0x67e37601
        0x67d26cc4
        0x67c12ed0
        0x67b05475
        0x679fc4ea
        0x678e9933
        0x677d8181
        0x676c8df3
        0x675b5407
        0x674a7280
        0x6739a97e
        0x672854be
        0x671772cb
        0x6706f5d5
        0x66f5dd73
        0x66e41ace
        0x66d3ce74
        0x66c2fcde
        0x66b12e0e
        0x66a0717e
        0x668f6a4f
        0x667e9da8
        0x666d610b
        0x665cfaf0
        0x664bcecb
        0x663afe4a
        0x6629571c  # 1.999217E23f
        0x66189fd2
        0x6607d685
        0x65f68bc7
        0x65e592ec
        0x65d45b20
        0x65c3ad45
        0x65b2e9a3
        0x65a1966f
        0x6590681f
        0x657f5344
        0x656e054c
        0x655d02e0
        0x654c6190
        0x653becb2
    .end array-data

    :array_3fc
    .array-data 4
        0x237c17d2
        0x236bca1f
        0x235acbd3
        0x2349941b
        0x2338ad05
        0x232717b6
        0x2316d060
        0x2305cedb
        0x22f488a5
        0x22e3933f
        0x22d2dd1b
        0x22c198ed
        0x22b0d8a0
        0x229f0b21
        0x228e33f6
        0x227d8532
        0x226cc5dc
        0x225b43e3
        0x224ae0cf
        0x2239b583
        0x2228c70b
        0x2217deba
        0x22064ef6
        0x21f5a55d
        0x21e48718
        0x21d360db
        0x21c27685
        0x21b1c5a8
        0x21a0ca84
        0x218ffb32
        0x217ecbcc
        0x216d841e
        0x215cded0
        0x214bbd8b
        0x213a4bab
        0x212930da
        0x21180483
        0x21076a55
        0x20f6a821
        0x20e589de
        0x20d406eb
        0x20c3bc2f
        0x20b20bcb
        0x20a1c6b7
        0x2090cf82
        0x207f524e
        0x206ebcac
        0x205d5d72
    .end array-data

    :array_460
    .array-data 8
        0x1d8ab6b643beL
        0xf73a94c7d1dL
        0x5c15908fcbcL
        0x6a2d70688379L
        0xbdd9c8d096bL
        0x1bc2e57f1a57L
        0x3e75ee34636fL
        0x1310c79ed6bdL
        0x6589f389183L
        0x26c02cb02e40L
        0x504387373fd7L
        0x56973de3f7aL
        0x20eb8830b26L
        0x45d4543d75aaL
    .end array-data

    :array_49c
    .array-data 8
        0x5c3e8cc8e99bL
        0xde3d5c04c86L
        0x5fbeffa53322L
        0x1695b25d8e9L
        0x411334bb2c95L
        0x2db09bb1b056L
        0x4cab8411eda5L
        0x2c298b0e9fe5L
        0x586387a42ff6L
        0x5bb556294faL
        0x6a49404526b8L
        0x4387f5237c96L
    .end array-data

    :array_4d0
    .array-data 4
        -0x3e1e5dca
        -0x3e0de6ac
        -0x3dfc59e4
        -0x3debb3c3
        -0x3dda3e07
        -0x3dc95245
        -0x3db886a7
        -0x3da7f34d
        -0x3d965a03
        -0x3d85eb9c
        -0x3d744d29
        -0x3d6323da
        -0x3d52a1a6
        -0x3d41a3c5
        -0x3d301890
        -0x3d1f063c
        -0x3d0e47d2
        -0x3cfd81ef
        -0x3cec013e
        -0x3cdb89f9
        -0x3cca669e
        -0x3cb95fb3
        -0x3ca862c3
        -0x3c97e142
        -0x3c860329
        -0x3c75213e
        -0x3c647adc
        -0x3c534de2
        -0x3c42db5a
        -0x3c31f20e
        -0x3c209c56
        -0x3c0f0b7c
        -0x3bfeaf06
        -0x3bed29c5
        -0x3bdc568d
        -0x3bcb7788
        -0x3bba9b14
        -0x3ba947c7
        -0x3b9836c6
        -0x3b87e5c8
        -0x3b7620b3
        -0x3b65536a
        -0x3b5489e7
        -0x3b435486
        -0x3b32afd8
        -0x3b215b81
        -0x3b10031e
        -0x3affc16e
        -0x3aee90af
        -0x3add4a9b
        -0x3accac09
        -0x3abbaade
        -0x3aaa7825
        -0x3a999f64
        -0x3a8864c5
        -0x3a77fd32
    .end array-data

    :array_544
    .array-data 8
        0x274b164e20f5L
        0x70f3e35095d7L
        0x140ae7571000L
        0x630925644badL
        0x73e6580574d5L
        0x4cc82224c486L
        0x582f45ec618aL
        0x5e9ab5061332L
        0x46883720ade7L
        0x435f2c824c66L
        0x58be5d29b3baL
        0x304e19d24582L
    .end array-data

    :array_578
    .array-data 4
        -0x66904b49
        -0x667f1bfa
        -0x666e6aa8
        -0x665d14ea
        -0x664cd494
        -0x663b0ed6
        -0x662a337b
        -0x6619a789
        -0x66081eb6
        -0x65f7b75f  # -2.818281E-23f
        -0x65e6bbec
        -0x65d5929e
        -0x65c4475e
        -0x65b3f1d2
        -0x65a29114
        -0x659110fc
        -0x6580c3b5
        -0x656f574a
        -0x655ef15c
        -0x654d2563
        -0x653c9562
        -0x652b18fb
        -0x651a0f4c
        -0x6509e4df
        -0x64f83b62
        -0x64e724a8
        -0x64d60546
        -0x64c56dc0
        -0x64b4e7ef
        -0x64a3895f
        -0x649274c6
        -0x6481f0b2
        -0x6470df5d
        -0x645facfd
        -0x644e5fbd
        -0x643d5efb
        -0x642c3644
        -0x641b514b
        -0x640a2ab3
        -0x63f977f7
        -0x63e84424
        -0x63d70aa7
        -0x63c6017c
        -0x63b520eb
        -0x63a47d4d
        -0x6393858a
        -0x63822014  # -8.400009E-22f
        -0x63715dcf
        -0x6360b0e7
        -0x634f63df
        -0x633eb4cb
        -0x632df547
        -0x631cada1
        -0x630b45d4
        -0x62fa69ce
        -0x62e93301
    .end array-data

    :array_5ec
    .array-data 8
        0x13b48d003890L
        0x2778d0a7bec0L
        0x7b1b7d017a6cL
        0x1d7a8fd095a4L
        0x2020ee41b0cfL
        0x35f371d8f6faL
        0x5dfaee3a7ba7L
        0x1a5673c392daL
        0x26e04f60f770L
        0x335ad7bd15f6L
        0x3650655d6f49L
        0x664626d37499L
    .end array-data

    :array_620
    .array-data 8
        0x68d66673339aL
        0x42eb893fa374L
        0xfcb0424a781L
        0x39b5a9ea6d3bL
        0x745222f0adf9L
        0x8e1709c2a8cL
        0x4bf6b64c5442L
        0x2581239a608aL
        0x7e1ae8a72672L
        0x2c6057e1d04aL
        0x21d93b8dcc1dL
        0x3d76f3237bccL
        0x15d24ccf0783L
        0x41738a72b849L
    .end array-data

    :array_65c
    .array-data 8
        0x5e3992869265L
        0x69f2e76927fcL
        0x56fb26a39413L
        0x27c006c83a19L
        0x43b2275a89d5L
        0x43dc8b65be34L
        0x48f4821e5284L
        0x405ba3e75d84L
        0x5b1a115644b3L
        0x49ca1988b1d8L
        0x120ed9d52b6eL
        0x26e515314288L
    .end array-data

    :array_690
    .array-data 8
        0x1b37862d91e1L
        0x4124b2d5e070L
        0x3bb546fc6825L
        0x5eea0f442f9dL
        0x1bbc1213076dL
        0x6664f17dae96L
        0x4dbbf7c38da1L
        0x116ca0b55d7eL
        0x7210b1004022L
        0x710a0c56ee76L
        0x7192ffbf5a50L
        0x6e3279bbb674L
        0x295d374bfa34L
        0x4ebc85e134abL
    .end array-data

    :array_6cc
    .array-data 4
        -0x5d94bf25
        -0x5da5c6c9
        -0x5db68783
        -0x5dc7176e
        -0x5dd85660
        -0x5de967dc
        -0x5dfae05b
        -0x5e0b2abb
        -0x5e1cf958
        -0x5e2db55c
        -0x5e3e0c4c
        -0x5e4f6183
        -0x5e60438f
        -0x5e71aaf7
        -0x5e82130d
        -0x5e93b577
        -0x5ea4e0b1
        -0x5eb57d97
        -0x5ec6dcc7
        -0x5ed73f27
        -0x5ee8fb13
        -0x5ef9925f
        -0x5f0ab425
        -0x5f1b116b
        -0x5f2c3750
        -0x5f3d662a
        -0x5f4e1115
        -0x5f5f34bb
        -0x5f7093e9
        -0x5f8155e6
        -0x5f92caf7
        -0x5fa30c1c
        -0x5fb4766a
        -0x5fc50f23
        -0x5fd6ac0f
        -0x5fe7153a
        -0x5ff82be7
        -0x6009bcea
        -0x601a317e
        -0x602b622d
        -0x603c9c88
        -0x604d5e7e
        -0x605e48f2
        -0x606f13d0
        -0x6080274e
        -0x6091040f
        -0x60a29af8
        -0x60b3719e
    .end array-data

    :array_730
    .array-data 8
        0xfe4327d44a7L
        0x851e247de4cL
        0x547a21d5c0c1L
        0x295ae29aa097L
        0x34d7af4659e9L
        0x2d562820046cL
        0xa7c0000a679L
    .end array-data

    :array_750
    .array-data 4
        0xe60cb28
        0xe710204
        0xe820330
        0xe9374eb
        0xea4dae0
        0xeb5b324
        0xec68403
        0xed75ddd
        0xee862d1
        0xef9b5c6
        0xf0a5e17
        0xf1b1759
        0xf2cccb1
        0xf3d34be
        0xf4e60d9
        0xf5fd6bf
        0xf70d2b1
        0xf81eca8
    .end array-data
.end method

.method private static e(Ljava/lang/String;I)Ljava/lang/Boolean;
    .registers 8

    const p1, 0xd9cd672

    const/4 v0, 0x0

    .line 38
    invoke-static {p1, v0}, Lcom/wukong/manager/cy;->h(ILjava/lang/Object;)I

    .line 39
    invoke-static {p0}, Landroid/text/TextUtils;->isEmpty(Ljava/lang/CharSequence;)Z

    move-result p1

    if-eqz p1, :cond_f

    goto/16 :goto_8d

    .line 71
    :cond_f
    :try_start_f
    sget-object p1, Lcom/wukong/manager/WukongPackageManagerHook;->i:Ljava/lang/reflect/Method;

    if-nez p1, :cond_15

    :catchall_13
    move-object p1, v0

    goto :goto_1b

    .line 74
    :cond_15
    invoke-virtual {p1, v0, v0}, Ljava/lang/reflect/Method;->invoke(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;

    move-result-object p1

    check-cast p1, Ljava/lang/String;
    :try_end_1b
    .catchall {:try_start_f .. :try_end_1b} :catchall_13

    .line 44
    :goto_1b
    :try_start_1b
    sget-object v1, Lcom/wukong/manager/WukongPackageManagerHook;->f:Ljava/lang/String;

    invoke-virtual {v1, p1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result p1

    if-eqz p1, :cond_8d

    .line 45
    invoke-static {}, Lcom/wukong/manager/WukongInstrumentationHook;->isPhotosEnabledForCurrentProcess()Z

    move-result p1

    if-nez p1, :cond_2b

    goto/16 :goto_8d

    .line 49
    :cond_2b
    sget-object p1, Lcom/wukong/manager/WukongPackageManagerHook;->g:[Ljava/lang/String;

    const/4 v1, 0x0

    const/4 v2, 0x1

    if-eqz p1, :cond_45

    if-nez p0, :cond_34

    goto :goto_45

    .line 84
    :cond_34
    array-length v3, p1

    move v4, v1

    :goto_36
    if-ge v4, v3, :cond_45

    aget-object v5, p1, v4

    .line 85
    invoke-virtual {p0, v5}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v5

    if-eqz v5, :cond_42

    move p1, v2

    goto :goto_46

    :cond_42
    add-int/lit8 v4, v4, 0x1

    goto :goto_36

    :cond_45
    :goto_45
    move p1, v1

    :goto_46
    if-eqz p1, :cond_4d

    .line 50
    sget-object p0, Ljava/lang/Boolean;->TRUE:Ljava/lang/Boolean;

    return-object p0

    :catchall_4b
    move-exception p1

    goto :goto_6a

    .line 52
    :cond_4d
    sget-object p1, Lcom/wukong/manager/WukongPackageManagerHook;->h:[Ljava/lang/String;

    if-eqz p1, :cond_65

    if-nez p0, :cond_54

    goto :goto_65

    .line 84
    :cond_54
    array-length v3, p1

    move v4, v1

    :goto_56
    if-ge v4, v3, :cond_65

    aget-object v5, p1, v4

    .line 85
    invoke-virtual {p0, v5}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v5

    if-eqz v5, :cond_62

    move v1, v2

    goto :goto_65

    :cond_62
    add-int/lit8 v4, v4, 0x1

    goto :goto_56

    :cond_65
    :goto_65
    if-eqz v1, :cond_8d

    .line 53
    sget-object p0, Ljava/lang/Boolean;->FALSE:Ljava/lang/Boolean;
    :try_end_69
    .catchall {:try_start_1b .. :try_end_69} :catchall_4b

    return-object p0

    .line 56
    :goto_6a
    new-instance v1, Ljava/lang/StringBuilder;

    invoke-direct {v1}, Ljava/lang/StringBuilder;-><init>()V

    const/4 v2, 0x6

    new-array v2, v2, [J

    fill-array-data v2, :array_8e

    const v3, 0x7a37aa04

    const/16 v4, 0x18

    invoke-static {v2, v3, v4}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v1, p0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p0

    sget-object v1, Lcom/wukong/manager/WukongPackageManagerHook;->e:Ljava/lang/String;

    invoke-static {v1, p0, p1}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I

    :cond_8d
    :goto_8d
    return-object v0

    :array_8e
    .array-data 8
        0x5ef6ad71d5e5L
        0x67f9d7045714L
        0x3d93abe950ceL
        0x1aec00da8bd4L
        0x60e800aee33fL
        0x6939ca8fda1eL
    .end array-data
.end method

.method public static maybeOverride(Ljava/lang/String;I)Ljava/lang/Boolean;
    .registers 4

    const/4 v0, 0x0

    const v1, 0x18825d68

    .line 93
    invoke-static {v1, v0}, Lcom/wukong/manager/cy;->h(ILjava/lang/Object;)I

    move-result v0

    .line 94
    invoke-static {v0, v1}, Lcom/wukong/manager/cy;->i(II)Z

    move-result v0

    if-eqz v0, :cond_13

    .line 95
    invoke-static {p0, p1}, Lcom/wukong/manager/WukongPackageManagerHook;->e(Ljava/lang/String;I)Ljava/lang/Boolean;

    move-result-object p0

    return-object p0

    .line 97
    :cond_13
    sget-object p0, Ljava/lang/Boolean;->FALSE:Ljava/lang/Boolean;

    return-object p0
.end method
