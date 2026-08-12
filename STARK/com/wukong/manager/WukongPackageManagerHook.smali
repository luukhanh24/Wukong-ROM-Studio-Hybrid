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
    .registers 19

    const/16 v0, 0x14

    .line 8
    new-array v0, v0, [I

    fill-array-data v0, :array_14e

    const v1, 0x191f3ad8

    invoke-static {v0, v1}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/WukongPackageManagerHook;->e:Ljava/lang/String;

    const/16 v0, 0x8

    .line 9
    new-array v0, v0, [J

    fill-array-data v0, :array_17a

    const v1, 0x119be04

    const/16 v2, 0x1e

    invoke-static {v0, v1, v2}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/WukongPackageManagerHook;->f:Ljava/lang/String;

    const/16 v0, 0xb

    .line 10
    new-array v1, v0, [J

    fill-array-data v1, :array_19e

    const v2, 0x264ceee7

    const/16 v3, 0x2c

    .line 11
    invoke-static {v1, v2, v3}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v1

    new-array v0, v0, [J

    fill-array-data v0, :array_1ce

    const v2, 0x23f62e31

    .line 12
    invoke-static {v0, v2, v3}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v0

    filled-new-array {v1, v0}, [Ljava/lang/String;

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/WukongPackageManagerHook;->g:[Ljava/lang/String;

    const/16 v0, 0x31

    .line 14
    new-array v1, v0, [I

    fill-array-data v1, :array_1fe

    const v2, 0x38d31a0d

    .line 15
    invoke-static {v1, v2}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v3

    const/16 v1, 0xd

    new-array v1, v1, [J

    fill-array-data v1, :array_264

    const v2, 0x3a45bc84

    .line 16
    invoke-static {v1, v2, v0}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v4

    const/16 v1, 0x39

    new-array v1, v1, [I

    fill-array-data v1, :array_29c

    const v2, 0x3d21459c

    .line 17
    invoke-static {v1, v2}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v5

    new-array v0, v0, [I

    fill-array-data v0, :array_312

    const v1, 0x5fdc73d

    .line 18
    invoke-static {v0, v1}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v6

    const/16 v0, 0x38

    new-array v1, v0, [I

    fill-array-data v1, :array_378

    const v2, 0x3f1b4381

    .line 19
    invoke-static {v1, v2}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v7

    const/16 v1, 0x30

    new-array v2, v1, [I

    fill-array-data v2, :array_3ec

    const v8, 0x60e222e6

    .line 20
    invoke-static {v2, v8}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v8

    new-array v2, v0, [I

    fill-array-data v2, :array_450

    const v9, 0xb856ec2

    .line 21
    invoke-static {v2, v9}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v9

    new-array v2, v1, [I

    fill-array-data v2, :array_4c4

    const v10, 0x15ce399e

    .line 22
    invoke-static {v2, v10}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v10

    new-array v2, v0, [I

    fill-array-data v2, :array_528

    const v11, 0x46da4cfa

    .line 23
    invoke-static {v2, v11}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v11

    const/16 v2, 0xc

    new-array v12, v2, [J

    fill-array-data v12, :array_59c

    const v13, 0x4d57115f  # 2.2551499E8f

    .line 24
    invoke-static {v12, v13, v1}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v12

    new-array v13, v0, [I

    fill-array-data v13, :array_5d0

    const v14, 0x3a631ce6

    .line 25
    invoke-static {v13, v14}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v13

    new-array v14, v2, [J

    fill-array-data v14, :array_644

    const v15, 0x7cdc913a

    .line 26
    invoke-static {v14, v15, v1}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v14

    new-array v15, v0, [I

    fill-array-data v15, :array_678

    const v0, 0x44b5ff84

    .line 27
    invoke-static {v15, v0}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v15

    new-array v0, v2, [J

    fill-array-data v0, :array_6ec

    const v2, 0x1eb37d4a

    .line 28
    invoke-static {v0, v2, v1}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v0

    const/16 v2, 0xe

    new-array v2, v2, [J

    fill-array-data v2, :array_720

    move-object/from16 v17, v0

    const v0, 0x13b42096

    move-object/from16 v18, v3

    const/16 v3, 0x38

    .line 29
    invoke-static {v2, v0, v3}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v0

    new-array v1, v1, [I

    fill-array-data v1, :array_75c

    const v2, 0x7ba766a0

    .line 30
    invoke-static {v1, v2}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v1

    move-object/from16 v16, v17

    move-object/from16 v3, v18

    move-object/from16 v17, v0

    move-object/from16 v18, v1

    filled-new-array/range {v3 .. v18}, [Ljava/lang/String;

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/WukongPackageManagerHook;->h:[Ljava/lang/String;

    const/16 v0, 0x1a

    const/4 v1, 0x0

    .line 63
    :try_start_129
    new-array v0, v0, [I

    fill-array-data v0, :array_7c0

    const v2, 0x1c8abfb4

    invoke-static {v0, v2}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v0

    invoke-static {v0}, Ljava/lang/Class;->forName(Ljava/lang/String;)Ljava/lang/Class;

    move-result-object v0

    const/16 v2, 0x12

    new-array v2, v2, [I

    fill-array-data v2, :array_7f8

    const v3, 0x6a28cbd8

    invoke-static {v2, v3}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v0, v2, v1}, Ljava/lang/Class;->getMethod(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;

    move-result-object v1
    :try_end_14b
    .catchall {:try_start_129 .. :try_end_14b} :catchall_14b

    .line 32
    :catchall_14b
    sput-object v1, Lcom/wukong/manager/WukongPackageManagerHook;->i:Ljava/lang/reflect/Method;

    return-void

    :array_14e
    .array-data 4
        0x3c1bd96d
        0x3c0a097b
        0x3bf9f6ea
        0x3be8d7a1
        0x3bd722fc
        0x3bc66fd1
        0x3bb5070d
        0x3ba48da8
        0x3b93586c
        0x3b82a320
        0x3b71de7e
        0x3b60064a
        0x3b4f5cfa
        0x3b3e2400
        0x3b2dd360
        0x3b1cdbb4
        0x3b0b549e
        0x3afaee3c
        0x3ae97df9
        0x3ad8d54b
    .end array-data

    :array_17a
    .array-data 8
        0x4b9c31448124L
        0x660042afb0b4L
        0x68801739607bL
        0x2f8a8b40b60bL
        0x5c27eeb4a4ccL
        0x1077efab2b90L
        0x2456e0615b36L
        0x330200002190L
    .end array-data

    :array_19e
    .array-data 8
        0x2bc43cba30e5L
        0x64833deb447aL
        0x65e844e7bddaL
        0x6785db2d9b18L
        0x1468c7c9aa56L
        0x46c6d5b3dcc1L
        0x75dd5b8d911L
        0x3d708f3690d9L
        0x1069bf0ade9eL
        0x3ea9db916475L
        0x651402727a16L
    .end array-data

    :array_1ce
    .array-data 8
        0xeabd00d67e3L
        0xa4260ff7c5dL
        0x3b943d87f609L
        0x58c4c2247659L
        0x1d62bfb211d5L
        0x128159272f9L
        0x5ea8298bed5cL
        0x3b6b749d52a7L
        0x2e3880adb237L
        0x582166082f1bL
        0x38c7721ff9cbL
    .end array-data

    :array_1fe
    .array-data 4
        0x1a0d07df
        0x1a1ec1c3
        0x1a2fb66b
        0x1a40e43f
        0x1a514517
        0x1a62f186
        0x1a73574d
        0x1a844e15
        0x1a95ad56
        0x1aa69291
        0x1ab758cb
        0x1ac8062b
        0x1ad9b28d
        0x1aeac5ed
        0x1afbdfce
        0x1b0c0316
        0x1b1db451
        0x1b2e8481
        0x1b3f9d2c
        0x1b504f26
        0x1b61389f
        0x1b72b3c1
        0x1b834ad1
        0x1b944124
        0x1ba56ffe
        0x1bb60e52
        0x1bc76337
        0x1bd88ff2
        0x1be91be6
        0x1bfafa9f
        0x1c0b19ee
        0x1c1c5ae5
        0x1c2d5dda
        0x1c3efc89
        0x1c4f86e9
        0x1c604cc8
        0x1c71c345  # 7.999259E-22f
        0x1c823c2c
        0x1c933833
        0x1ca4d748
        0x1cb5efed
        0x1cc6477e
        0x1cd76f24
        0x1ce881ae
        0x1cf92023
        0x1d0aac61
        0x1d1b87e0
        0x1d2c3c37
        0x1d3ddc09
    .end array-data

    :array_264
    .array-data 8
        0x15b27dad8bc4L
        0x69ac7b3fbbd3L
        0x112d2310f456L
        0x79bb26a46264L
        0x29886f4b1936L
        0x3bf24c98474aL
        0x3ae4f6402ea6L
        0x3ae87f23d653L  # 3.20007503969816E-310
        0x1b9cd7453745L  # 1.50000506365926E-310
        0x474d1e1f3f4fL
        0x63ff365f2a2eL
        0x194e6b121e81L
        0x593c000000e3L
    .end array-data

    :array_29c
    .array-data 4
        0x4954a736  # 871027.4f
        0x4943b553
        0x493240ac  # 730122.75f
        0x492194b7
        0x49103e80  # 590824.0f
        0x48ff7931
        0x48ee4d1b
        0x48ddc5e1
        0x48cc5e7b
        0x48bbef04  # 384888.12f
        0x48aa4435
        0x4899c84f
        0x48882266
        0x4877c22b
        0x4866860d
        0x4855283f
        0x4844b25a
        0x4833a6f0  # 183963.75f
        0x4822536a
        0x4811eca4
        0x480086cf
        0x47ef3b0b
        0x47de0b14
        0x47cd34a9
        0x47bcd3d4
        0x47ab4e06
        0x479ac5d0  # 79243.625f
        0x478901b2
        0x477849fb
        0x476729fc
        0x475614d2
        0x4745bcf0  # 50620.938f
        0x4734087f
        0x4723226b
        0x4712057d
        0x4701d172
        0x46f0fba3
        0x46df4878
        0x46ce363c
        0x46bd2ecc
        0x46acdd4c
        0x469b0d54
        0x468ac38d
        0x4679030b
        0x466810f2
        0x4657ae47
        0x464654bb
        0x4635b26f
        0x4624b04e
        0x46136607
        0x4602167a
        0x45f18bd5
        0x45e05f87
        0x45cf8c27
        0x45be7602
        0x45ad6c8a
        0x459caa7b
    .end array-data

    :array_312
    .array-data 4
        -0x3592106d
        -0x35a34c3d
        -0x35b4b363
        -0x35c5825f
        -0x35d6c9bf
        -0x35e72330  # -2504500.0f
        -0x35f8794c  # -2220461.0f
        -0x36093e5a
        -0x361a01b8  # -1884105.0f
        -0x362b4277
        -0x363c4ca2
        -0x364dd34e
        -0x365e9533
        -0x366f8f99
        -0x3680d90b
        -0x3691f0cd
        -0x36a28698  # -907158.5f
        -0x36b38826
        -0x36c4f759
        -0x36d5da56
        -0x36e6d97f
        -0x36f70675
        -0x3708ecdb
        -0x3719af92
        -0x372a1efe
        -0x373beb9f
        -0x374c782f
        -0x375da1d7
        -0x376e857f
        -0x377f5450  # -263517.5f
        -0x379068b5
        -0x37a1d8da
        -0x37b2104f
        -0x37c377c7
        -0x37d4b9f8
        -0x37e58527
        -0x37f66dd9
        -0x3807708d
        -0x38187203
        -0x3829d958
        -0x383a773e
        -0x384b132b
        -0x385cab90  # -83624.875f
        -0x386d0c43
        -0x387e0407
        -0x388fc4e6
        -0x38a055d9
        -0x38b1e3d1
        -0x38c2c602
    .end array-data

    :array_378
    .array-data 4
        0x4728f434
        0x4717a3e0  # 38819.875f
        0x4706e65d
        0x46f59aee
        0x46e4f553
        0x46d3a086
        0x46c2fa5b
        0x46b19a29
        0x46a02387
        0x468f558c
        0x467e28a1
        0x466d4748
        0x465c5419
        0x464b27d0
        0x463a8df6
        0x46293c7f
        0x4618e0ed
        0x46072a2c
        0x45f6aad4
        0x45e57b77
        0x45d4e9f3
        0x45c3e82c
        0x45b2e127
        0x45a19b47
        0x4590395d
        0x457fa519
        0x456e1f13
        0x455d54c5
        0x454ca737
        0x453b6816
        0x452a6cf9
        0x4519251b
        0x4508fb45
        0x44f7ae29
        0x44e6a2a4
        0x44d583dc
        0x44c4098c
        0x44b3ed32
        0x44a25069
        0x4491d936
        0x44809783
        0x446ff4c5
        0x445e6b52
        0x444dd072
        0x443c6084
        0x442ba5bf
        0x441a0148
        0x4409cd8b
        0x43f86f69
        0x43e7fd1a
        0x43d6c851
        0x43c5f0dd
        0x43b48e16
        0x43a30350
        0x43921348
        0x43810c94
    .end array-data

    :array_3ec
    .array-data 4
        0x22e6628e
        0x22f75059
        0x23088162  # 7.399973E-18f
        0x2319a7b3
        0x232af1d4
        0x233bbac5
        0x234ce7be
        0x235d03ba
        0x236e4b9f
        0x237fa589
        0x23908332
        0x23a10ba1
        0x23b2338c
        0x23c3f229
        0x23d4d969
        0x23e5d0ed
        0x23f6e39c
        0x2407f341
        0x24187ea1
        0x24291166
        0x243a3cb5
        0x244b929c
        0x245ca521
        0x246d513a
        0x247ee3be
        0x248fa839
        0x24a09ee6
        0x24b17a51
        0x24c296cb
        0x24d3f899
        0x24e49c16
        0x24f59672
        0x2506c080
        0x2517bcee
        0x25288c7b
        0x2539fe08
        0x254a58fe
        0x255bee9a
        0x256c03fe
        0x257daf7d
        0x258ee7d1
        0x259f5dbd
        0x25b05a70
        0x25c15a65
        0x25d24aa1
        0x25e364f0
        0x25f4cbf5
        0x2605d59d
    .end array-data

    :array_450
    .array-data 4
        0x72691feb  # 4.61751E30f
        0x72581e48
        0x72478cb0
        0x7236b0fb
        0x72251021
        0x7214ce62
        0x7203aac2
        0x71f23149
        0x71e1c2ea
        0x71d04aab
        0x71bf1d80
        0x71ae6d45
        0x719d6c7d
        0x718c52a4
        0x717b0a22
        0x716aec69
        0x7159496d
        0x714875d9
        0x7137679f
        0x7126da60
        0x7115790e
        0x7104f3a0
        0x70f3f17f
        0x70e2cee3
        0x70d12875
        0x70c0dd51
        0x70af39eb
        0x709e4b50
        0x708d07d1
        0x707c8015
        0x706bdc61
        0x705ac896
        0x7049635d
        0x7038d902
        0x7027da03
        0x70167ee6
        0x70050a3c
        0x6ff41141
        0x6fe3ade6
        0x6fd2bc83
        0x6fc1551b
        0x6fb02799
        0x6f9f2de7
        0x6f8eb8ec
        0x6f7d931c
        0x6f6c7a5a
        0x6f5bf014
        0x6f4a09b5
        0x6f39518e
        0x6f285df0
        0x6f171c24
        0x6f065613
        0x6ef56e98
        0x6ee43ce1
        0x6ed344db
        0x6ec22ada
    .end array-data

    :array_4c4
    .array-data 4
        0x3cbd88de
        0x3cac31b0
        0x3c9b95bd
        0x3c8a60e8
        0x3c792be1
        0x3c6843fb
        0x3c576cfb
        0x3c4654ba
        0x3c350aaa
        0x3c2492af
        0x3c1376fd  # 0.009000537f
        0x3c028a20
        0x3bf1e2ef
        0x3be039d3
        0x3bcfc75d
        0x3bbea990
        0x3bad8687
        0x3b9c52c0
        0x3b8bc70f
        0x3b7a39cb
        0x3b693cae
        0x3b58acdd
        0x3b47ec4c
        0x3b36318f
        0x3b25f8b2
        0x3b14a919
        0x3b036402
        0x3af28748
        0x3ae15af7
        0x3ad028d2
        0x3abf95fc
        0x3aaeb136
        0x3a9d5391
        0x3a8c4c5e
        0x3a7b8706
        0x3a6a7c16
        0x3a5928b2
        0x3a48f4d8
        0x3a37fa2c
        0x3a26e802
        0x3a154cd7
        0x3a043f39
        0x39f37189
        0x39e25f34
        0x39d19163
        0x39c0c6cf
        0x39af79e8
        0x399ee265
    .end array-data

    :array_528
    .array-data 4
        0x50a1b52d
        0x5090f0a3
        0x507f6138
        0x506ef19b
        0x505d8211
        0x504cdb3d
        0x503b44c8
        0x502a65bd
        0x50196680
        0x500880f4
        0x4ff7dd53
        0x4fe6e4a2  # 7.7474867E9f
        0x4fd5f865
        0x4fc4e111
        0x4fb3fbc5
        0x4fa2c4fd
        0x4f913801
        0x4f809664
        0x4f6fb0f0  # 4.0213504E9f
        0x4f5e4ca7  # 3.7295654E9f
        0x4f4d8225
        0x4f3c906f
        0x4f2b57ec
        0x4f1addec
        0x4f09ec09
        0x4ef8fb3f
        0x4ee73cb3  # 1.9397574E9f
        0x4ed68d4f
        0x4ec59e20
        0x4eb43332
        0x4ea330ba
        0x4e9281ab
        0x4e81f86d
        0x4e709606
        0x4e5f7159  # 9.371869E8f
        0x4e4ea407  # 8.6671405E8f
        0x4e3d50b8  # 7.9404595E8f
        0x4e2c6096  # 7.2300275E8f
        0x4e1bc92e  # 6.5341325E8f
        0x4e0aabcf  # 5.8162886E8f
        0x4df93871  # 5.2265322E8f
        0x4de8c2e2  # 4.8813574E8f
        0x4dd78e2a  # 4.520523E8f
        0x4dc67b5a  # 4.162466E8f
        0x4db50cc5  # 3.7968912E8f
        0x4da467a9  # 3.447821E8f
        0x4d9346e6  # 3.0886214E8f
        0x4d828e1a
        0x4d71629d  # 2.5311074E8f
        0x4d60ccbc
        0x4d4f8f6c  # 2.1764269E8f
        0x4d3ee115  # 2.0015138E8f
        0x4d2d32e9  # 1.8161218E8f
        0x4d1c4243  # 1.6384926E8f
        0x4d0b42f4  # 1.460263E8f
        0x4cfa256c  # 1.3114864E8f
    .end array-data

    :array_59c
    .array-data 8
        0x2a6b37f99daL
        0x43045da9ca28L
        0x4fdac123fa0eL
        0x5b47be005d0fL
        0x62d9a5e8c5f3L
        0x19f1e924dba5L
        0x286b77df822aL
        0x2e36d96f2b8aL
        0x759f42734edfL
        0x319050bcdf1cL
        0x38659203199cL
        0x2c02608996d8L
    .end array-data

    :array_5d0
    .array-data 4
        0x208dcc40
        0x207c061e
        0x206b1449
        0x205abe17
        0x204903a7
        0x2038db7d
        0x2027d22e
        0x201685a1
        0x2005b6d6
        0x1ff4ad4d
        0x1fe32bd0
        0x1fd2d142
        0x1fc1a26e
        0x1fb04dad
        0x1f9f505d
        0x1f8eb745
        0x1f7d55cc
        0x1f6c4c5e
        0x1f5b0a5c
        0x1f4acccd
        0x1f395b2c
        0x1f284414
        0x1f170ccd
        0x1f0681b9
        0x1ef5fc22
        0x1ee45bc3
        0x1ed32a62
        0x1ec2aee5
        0x1eb17c8b
        0x1ea0e1aa
        0x1e8f1e5a
        0x1e7e0b6f
        0x1e6d58bc
        0x1e5cb739
        0x1e4b1676
        0x1e3a2cfa
        0x1e292ec6
        0x1e1882be
        0x1e072339
        0x1df6beea
        0x1de5afbc
        0x1dd47f36
        0x1dc3ce8e
        0x1db2f11b
        0x1da18b6a
        0x1d90f2f3
        0x1d7f90aa
        0x1d6e04e1
        0x1d5d0d68
        0x1d4c3481
        0x1d3b0f88
        0x1d2a2431
        0x1d194e92  # 2.0290001E-21f
        0x1d08a74b
        0x1cf77bcf
        0x1ce68955
    .end array-data

    :array_644
    .array-data 8
        0x60f48b55db20L
        0x53d84d9868d2L
        0x58c87c638ae6L
        0x1230c577a91aL
        0x4c565a114f8L
        0x69e480031378L
        0x47c0e609b3dfL
        0x103b8a674fb6L
        0x3d29fd25a089L
        0x758c7a59a019L
        0x1bedf1d36ce7L
        0x11e697dcb570L
    .end array-data

    :array_678
    .array-data 4
        0x32b2a83
        0x31a4b2e
        0x3091ec1
        0x2f8daec
        0x2e7745f
        0x2d61a96
        0x2c5f532
        0x2b40abb
        0x2a3c9ae
        0x29227ac
        0x281a276
        0x27049f6
        0x25fd3fb
        0x24ef805
        0x23dbb07
        0x22cb06d
        0x21b3c15
        0x20a8b39
        0x1f933ec
        0x1e89b52
        0x1d7c0a5
        0x1c67a63
        0x1b50ea0
        0x1a48af0
        0x193767b
        0x182fa1e
        0x1716380
        0x1606b6d
        0x14f79b4
        0x13ea550
        0x12dcbf9
        0x11ce70c
        0x10ba93f
        0xfa3c10
        0xe9f9c4
        0xd8042f
        0xc7895c
        0xb69fb0
        0xa51616
        0x94df3b
        0x839b9e
        0x72b707
        0x61dcea
        0x508a17
        0x3f81bc
        0x2ec033
        0x1dfec3
        0xc955d
        -0x49b5e
        -0x1536c4
        -0x2651db
        -0x3754e7
        -0x480f74
        -0x5913cf
        -0x6aed46
        -0x7b51ed
    .end array-data

    :array_6ec
    .array-data 8
        0x32c6fe125419L
        0x3c3111efb775L
        0x5b6576714352L
        0x45889e271d38L
        0x4873e73b65c9L
        0x124dffa83efcL
        0x2d8002d73379L
        0x5cea275dc989L
        0x4f41996d98aeL
        0x4c1a8922e562L
        0x7fb8d4f59430L
        0x5c7354801578L
    .end array-data

    :array_720
    .array-data 8
        0x3b557dbbbb03L
        0x2928b4d7aa8cL
        0x7ffcf6afbe7eL
        0x44830ef6b44L
        0x4ea0a60b4909L
        0x413b23288098L
        0x4943ea966e4L
        0x5a9777d3e4deL
        0x7e22275d0393L
        0x66785a0373a8L
        0x37690eb8132L
        0x57b4807e6108L
        0x7b6b80029a59L
        0xfe44514d8b8L
    .end array-data

    :array_75c
    .array-data 4
        0x69bf2ad3
        0x69ae4ba7
        0x699dc54d
        0x698cf5c1
        0x697b3b4c
        0x696a9cc2
        0x69592aa6
        0x69481115
        0x69372788
        0x6926b82b
        0x691530b2
        0x6904c734
        0x68f323e0
        0x68e26709
        0x68d196d2
        0x68c0aaef
        0x68afa1a6
        0x689e1366
        0x688d35af
        0x687c9ec6
        0x686bec50
        0x685a0ab6
        0x684912bd
        0x6838ba52
        0x68278972
        0x6816afb4
        0x68057c3d
        0x67f4e997
        0x67e384e4
        0x67d2e0f9
        0x67c12e92
        0x67b03bf0
        0x679fc200
        0x678ee0d6
        0x677d6e50
        0x676cb44a
        0x675bf100
        0x674a31a7
        0x67396222
        0x6728d9e8
        0x671729f2
        0x6706eede
        0x66f5e04a
        0x66e4e351
        0x66d3520a
        0x66c241e4
        0x66b19229
        0x66a09420
    .end array-data

    :array_7c0
    .array-data 4
        -0x404b93d4
        -0x403a7550
        -0x4029def9
        -0x4018c06b
        -0x400773da
        -0x3ff6b9ad
        -0x3fe57466
        -0x3fd40cc5
        -0x3fc3f9e8
        -0x3fb2bee0  # -3.2071f
        -0x3fa107ed
        -0x3f901ef7
        -0x3f7f4832
        -0x3f6e8e8b
        -0x3f5d4ff8
        -0x3f4ca4dc
        -0x3f3b8991
        -0x3f2a026d
        -0x3f19d760
        -0x3f08d16f
        -0x3ef79762
        -0x3ee6b6d1
        -0x3ed5e1dd
        -0x3ec4196d
        -0x3eb34dc2
        -0x3ea2d6d0
    .end array-data

    :array_7f8
    .array-data 4
        -0x3427ae2f  # -2.8353442E7f
        -0x3416959c  # -3.0594248E7f
        -0x3405ec59  # -3.2778062E7f
        -0x33f4b2ef  # -3.6516932E7f
        -0x33e3842f  # -4.1021252E7f
        -0x33d219cf  # -4.5586628E7f
        -0x33c13b3b  # -5.0008852E7f
        -0x33b02840  # -5.4484736E7f
        -0x339f47eb  # -5.8908756E7f
        -0x338e17ba  # -6.341455E7f
        -0x337d9dc3  # -6.835863E7f
        -0x336c64a5  # -7.7388504E7f
        -0x335ba645  # -8.6167E7f
        -0x334aa11c  # -9.509046E7f
        -0x3339c34f  # -1.0393332E8f
        -0x3328adb2  # -1.1289048E8f
        -0x3317649d
        -0x3306ab4b
    .end array-data
.end method

.method private static e(Ljava/lang/String;I)Ljava/lang/Boolean;
    .registers 8

    const p1, 0x5ddb804b

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

    const v3, 0x1b4773a0

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
        0x6977ef321e1L
        0x7241938cec34L
        0x7549592538e7L
        0x2c22ecb442efL
        0x67bede4f1052L
        0x1084eee1796cL
    .end array-data
.end method

.method public static maybeOverride(Ljava/lang/String;I)Ljava/lang/Boolean;
    .registers 4

    const/4 v0, 0x0

    const v1, 0x6cbe6011

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
