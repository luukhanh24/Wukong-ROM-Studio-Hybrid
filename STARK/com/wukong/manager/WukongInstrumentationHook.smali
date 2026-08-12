.class public final Lcom/wukong/manager/WukongInstrumentationHook;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field public static final a:Ljava/lang/String;

.field public static aa:Z

.field public static ab:Z

.field public static ac:Z

.field public static ad:Z

.field public static final ae:Ljava/util/LinkedHashMap;

.field public static final af:Ljava/util/LinkedHashMap;

.field public static final b:Ljava/lang/String;

.field public static final c:Ljava/lang/String;

.field public static final d:Ljava/lang/String;

.field public static final e:Ljava/lang/String;

.field public static final f:Ljava/lang/String;

.field public static final g:Ljava/lang/String;

.field public static final h:Ljava/lang/String;

.field public static final i:Ljava/lang/String;

.field public static final j:Ljava/lang/String;

.field public static final k:Ljava/lang/String;

.field public static final l:Ljava/lang/String;

.field public static final m:Ljava/lang/String;

.field public static final n:Ljava/lang/String;

.field public static final o:Ljava/lang/String;

.field public static final p:Ljava/lang/String;

.field public static final q:Ljava/lang/String;

.field public static final r:[Ljava/lang/String;

.field public static final s:Ljava/lang/Object;

.field public static final t:Ljava/util/LinkedHashMap;

.field public static final u:Ljava/util/LinkedHashMap;

.field public static final v:Ljava/util/LinkedHashMap;

.field public static w:Z

.field public static x:J

.field public static y:Z

.field public static z:Z


# direct methods
.method static constructor <clinit>()V
    .registers 46

    const/16 v0, 0x15

    .line 16
    new-array v1, v0, [I

    fill-array-data v1, :array_4ca

    const v2, 0x79269c5e

    invoke-static {v1, v2}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v1

    sput-object v1, Lcom/wukong/manager/WukongInstrumentationHook;->e:Ljava/lang/String;

    .line 17
    new-array v0, v0, [I

    fill-array-data v0, :array_4f8

    const v1, 0x197cca19

    invoke-static {v0, v1}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->f:Ljava/lang/String;

    const/16 v0, 0x12

    .line 18
    new-array v0, v0, [I

    fill-array-data v0, :array_526

    const v1, 0x29b16d94

    invoke-static {v0, v1}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->g:Ljava/lang/String;

    const/16 v0, 0xd

    .line 19
    new-array v1, v0, [I

    fill-array-data v1, :array_54e

    const v2, 0x579640bd

    invoke-static {v1, v2}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v1

    sput-object v1, Lcom/wukong/manager/WukongInstrumentationHook;->h:Ljava/lang/String;

    const/16 v1, 0xa

    .line 20
    new-array v2, v1, [I

    fill-array-data v2, :array_56c

    const v3, 0x294ac8e6

    invoke-static {v2, v3}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v2

    sput-object v2, Lcom/wukong/manager/WukongInstrumentationHook;->i:Ljava/lang/String;

    const/4 v2, 0x4

    .line 21
    new-array v3, v2, [J

    fill-array-data v3, :array_584

    const v4, 0x3a2d6c0f

    invoke-static {v3, v4, v0}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v3

    sput-object v3, Lcom/wukong/manager/WukongInstrumentationHook;->a:Ljava/lang/String;

    const/4 v3, 0x5

    .line 22
    new-array v4, v3, [J

    fill-array-data v4, :array_598

    const v5, 0x68c9fbe3

    const/16 v6, 0x11

    invoke-static {v4, v5, v6}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v4

    sput-object v4, Lcom/wukong/manager/WukongInstrumentationHook;->b:Ljava/lang/String;

    const/4 v4, 0x2

    .line 23
    new-array v5, v4, [J

    fill-array-data v5, :array_5b0

    const v7, 0xcfdc2b2  # 3.9098E-31f

    const/16 v8, 0x8

    invoke-static {v5, v7, v8}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v5

    sput-object v5, Lcom/wukong/manager/WukongInstrumentationHook;->c:Ljava/lang/String;

    .line 24
    new-array v5, v2, [J

    fill-array-data v5, :array_5bc

    const v7, 0x7ee84490

    const/16 v9, 0x10

    invoke-static {v5, v7, v9}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v5

    sput-object v5, Lcom/wukong/manager/WukongInstrumentationHook;->d:Ljava/lang/String;

    .line 25
    new-array v5, v2, [J

    fill-array-data v5, :array_5d0

    const v7, 0x6a852f54

    invoke-static {v5, v7, v0}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->j:Ljava/lang/String;

    const/16 v0, 0xc

    .line 26
    new-array v5, v0, [I

    fill-array-data v5, :array_5e4

    const v7, 0xa266f52

    invoke-static {v5, v7}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v5

    sput-object v5, Lcom/wukong/manager/WukongInstrumentationHook;->k:Ljava/lang/String;

    const/16 v5, 0x13

    .line 27
    new-array v7, v5, [I

    fill-array-data v7, :array_600

    const v9, 0x3857895d

    invoke-static {v7, v9}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v7

    sput-object v7, Lcom/wukong/manager/WukongInstrumentationHook;->l:Ljava/lang/String;

    .line 28
    new-array v7, v5, [I

    fill-array-data v7, :array_62a

    const v9, 0x79fc6b9f

    invoke-static {v7, v9}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v7

    sput-object v7, Lcom/wukong/manager/WukongInstrumentationHook;->m:Ljava/lang/String;

    const/16 v7, 0x16

    .line 29
    new-array v7, v7, [I

    fill-array-data v7, :array_654

    const v9, 0x556b3734

    invoke-static {v7, v9}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v7

    sput-object v7, Lcom/wukong/manager/WukongInstrumentationHook;->n:Ljava/lang/String;

    const/16 v7, 0x1f

    .line 30
    new-array v7, v7, [I

    fill-array-data v7, :array_684

    const v9, 0x4b7d3c6c  # 1.6596076E7f

    invoke-static {v7, v9}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v7

    sput-object v7, Lcom/wukong/manager/WukongInstrumentationHook;->o:Ljava/lang/String;

    .line 31
    new-array v7, v6, [I

    fill-array-data v7, :array_6c6

    const v9, 0x51776f81

    invoke-static {v7, v9}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v7

    sput-object v7, Lcom/wukong/manager/WukongInstrumentationHook;->p:Ljava/lang/String;

    .line 32
    new-array v7, v8, [J

    fill-array-data v7, :array_6ec

    const v9, 0x201ebae5

    const/16 v10, 0x1e

    invoke-static {v7, v9, v10}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v7

    sput-object v7, Lcom/wukong/manager/WukongInstrumentationHook;->q:Ljava/lang/String;

    const v7, 0x160ddbfc

    const v9, 0x15fc8d7b

    const v10, 0x1640425b

    const v11, 0x162f83d0

    const v12, 0x161eebd4

    .line 33
    filled-new-array {v10, v11, v12, v7, v9}, [I

    move-result-object v7

    const v9, 0x744d15fc

    .line 34
    invoke-static {v7, v9}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v10

    new-array v7, v0, [I

    fill-array-data v7, :array_710

    const v9, 0x3dd0a146

    .line 35
    invoke-static {v7, v9}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v11

    const/4 v7, 0x6

    new-array v9, v7, [I

    fill-array-data v9, :array_72c

    const v12, 0x647fec3

    .line 36
    invoke-static {v9, v12}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v12

    const/4 v9, 0x7

    new-array v13, v9, [I

    fill-array-data v13, :array_73c

    const v14, 0x79ffef35

    .line 37
    invoke-static {v13, v14}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v13

    const v14, 0x2d502840

    const v15, 0x2d3f5106

    const v6, 0x2d83b9e4

    const v8, 0x2d727cc6

    const v3, 0x2d610b63

    filled-new-array {v6, v8, v3, v14, v15}, [I

    move-result-object v3

    const v6, 0xa532d3f

    .line 38
    invoke-static {v3, v6}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v14

    const v3, 0x4a94f5e3  # 4881137.5f

    const v6, 0x4a83a46d  # 4313654.5f

    const v8, 0x4ac76023  # 6533137.5f

    const v15, 0x4ab649f9  # 5973244.5f

    const v9, 0x4aa520f5  # 5410938.5f

    filled-new-array {v8, v15, v9, v3, v6}, [I

    move-result-object v3

    const v6, 0x731b4a83

    .line 39
    invoke-static {v3, v6}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v15

    const/16 v3, 0xf

    new-array v6, v3, [I

    fill-array-data v6, :array_74e

    const v8, 0xf22d6ae

    .line 40
    invoke-static {v6, v8}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v16

    new-array v6, v3, [I

    fill-array-data v6, :array_770

    const v8, 0x3f53e93f

    .line 41
    invoke-static {v6, v8}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v17

    const/16 v6, 0xb

    new-array v8, v6, [I

    fill-array-data v8, :array_792

    const v9, 0x1b87bd77

    .line 42
    invoke-static {v8, v9}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v18

    const v8, -0x4be69247

    const v9, -0x4bd5c897

    filled-new-array {v8, v9}, [I

    move-result-object v8

    const v9, 0x5ca2b419

    .line 43
    invoke-static {v8, v9}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v19

    new-array v5, v5, [I

    fill-array-data v5, :array_7ac

    const v8, 0x656bae86

    .line 44
    invoke-static {v5, v8}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v20

    const v5, 0x21beb063

    const v8, 0x21cf8e06

    const v9, 0x219cc419

    const v3, 0x21ad47fe

    filled-new-array {v9, v3, v5, v8}, [I

    move-result-object v3

    const v5, 0x268e219c

    .line 45
    invoke-static {v3, v5}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v21

    new-array v3, v1, [I

    fill-array-data v3, :array_7d6

    const v5, 0x45a639b1

    .line 46
    invoke-static {v3, v5}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v22

    const/4 v3, 0x1

    new-array v5, v3, [J

    const/4 v8, 0x0

    const-wide v23, 0x47271b23cbdaL

    aput-wide v23, v5, v8

    const v9, 0x4a78a255  # 4073621.2f

    .line 47
    invoke-static {v5, v9, v2}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v23

    const/16 v5, 0xe

    new-array v9, v5, [I

    fill-array-data v9, :array_7ee

    move/from16 v25, v8

    const v8, 0x5e22c75e

    .line 48
    invoke-static {v9, v8}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v24

    filled-new-array/range {v10 .. v24}, [Ljava/lang/String;

    move-result-object v8

    sput-object v8, Lcom/wukong/manager/WukongInstrumentationHook;->r:[Ljava/lang/String;

    .line 50
    new-instance v8, Ljava/lang/Object;

    invoke-direct {v8}, Ljava/lang/Object;-><init>()V

    sput-object v8, Lcom/wukong/manager/WukongInstrumentationHook;->s:Ljava/lang/Object;

    const v8, -0x6e54b9fd

    const v9, -0x6e437961

    const v10, -0x6e87e9e9

    const v11, -0x6e767855

    const v12, -0x6e653a75

    .line 51
    filled-new-array {v10, v11, v12, v8, v9}, [I

    move-result-object v8

    const v9, 0x40d89178

    .line 52
    invoke-static {v8, v9}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v26

    new-array v8, v7, [I

    fill-array-data v8, :array_80e

    const v9, 0x6c130f90

    invoke-static {v8, v9}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v27

    const/4 v8, 0x3

    new-array v9, v8, [J

    fill-array-data v9, :array_81e

    const v10, 0x7f37626c

    .line 53
    invoke-static {v9, v10, v0}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v28

    new-array v9, v4, [J

    fill-array-data v9, :array_82e

    const v10, 0x382b9b25

    invoke-static {v9, v10, v7}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v29

    new-array v9, v7, [I

    fill-array-data v9, :array_83a

    const v10, 0x30f70887

    .line 54
    invoke-static {v9, v10}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v30

    new-array v9, v7, [I

    fill-array-data v9, :array_84a

    const v10, 0x7ce23eb2

    invoke-static {v9, v10}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v31

    new-array v9, v4, [J

    fill-array-data v9, :array_85a

    const v10, 0x4433c460

    const/4 v11, 0x7

    .line 55
    invoke-static {v9, v10, v11}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v32

    new-array v9, v7, [I

    fill-array-data v9, :array_866

    const v10, 0x12db3bcd

    invoke-static {v9, v10}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v33

    const v9, 0x42beba25

    const v10, 0x42ad267e

    const v11, 0x42f149af

    const v12, 0x42e0e3ef

    const v13, 0x42cf79a2

    filled-new-array {v11, v12, v13, v9, v10}, [I

    move-result-object v9

    const v10, 0x767242ad

    .line 56
    invoke-static {v9, v10}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v34

    new-array v9, v5, [I

    fill-array-data v9, :array_876

    const v10, 0x40799762

    invoke-static {v9, v10}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v35

    new-array v9, v6, [I

    fill-array-data v9, :array_896

    const v10, 0x79edd928

    .line 57
    invoke-static {v9, v10}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v36

    const/16 v9, 0x42

    new-array v10, v9, [I

    fill-array-data v10, :array_8b0

    const v11, 0x3dcafe63

    invoke-static {v10, v11}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v37

    const v10, -0x29137c1d

    const v11, -0x2902b275

    filled-new-array {v10, v11}, [I

    move-result-object v10

    const v11, 0x78c1d6ec

    .line 58
    invoke-static {v10, v11}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v38

    const/16 v10, 0xf

    new-array v10, v10, [I

    fill-array-data v10, :array_938

    const v11, 0x2fad62c6

    invoke-static {v10, v11}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v39

    const v10, -0x7f46f543

    const v11, -0x7f57b932

    const v12, -0x7f24c7d7

    const v13, -0x7f358457

    filled-new-array {v12, v13, v10, v11}, [I

    move-result-object v10

    const v11, 0x1d1580a8

    .line 59
    invoke-static {v10, v11}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v40

    new-array v10, v8, [J

    fill-array-data v10, :array_95a

    const v11, 0xe0a8ab8

    invoke-static {v10, v11, v0}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v41

    new-array v10, v3, [J

    const-wide v11, 0x6a74266cc5a8L

    aput-wide v11, v10, v25

    const v11, 0x3a4d8766

    .line 60
    invoke-static {v10, v11, v2}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v42

    const v2, 0x391cf6e7

    const v10, 0x392da065

    const v11, 0x38fa2356

    const v12, 0x390b08e1

    filled-new-array {v11, v12, v2, v10}, [I

    move-result-object v2

    const v10, 0x1efb38fa

    invoke-static {v2, v10}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v43

    new-array v2, v5, [I

    fill-array-data v2, :array_96a

    const v5, 0x428e30b2

    .line 61
    invoke-static {v2, v5}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v44

    new-array v1, v1, [I

    fill-array-data v1, :array_98a

    const v2, 0x25cf0efa

    invoke-static {v1, v2}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v45

    filled-new-array/range {v26 .. v45}, [Ljava/lang/String;

    move-result-object v1

    .line 51
    invoke-static {v1}, Lcom/wukong/manager/WukongInstrumentationHook;->f([Ljava/lang/String;)Ljava/util/LinkedHashMap;

    move-result-object v1

    sput-object v1, Lcom/wukong/manager/WukongInstrumentationHook;->t:Ljava/util/LinkedHashMap;

    .line 63
    new-array v1, v4, [J

    fill-array-data v1, :array_9a2

    const v2, 0x791ca7f7

    const/4 v5, 0x5

    .line 64
    invoke-static {v1, v2, v5}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v10

    const/4 v11, 0x7

    new-array v1, v11, [I

    fill-array-data v1, :array_9ae

    const v2, 0x31dc448d

    invoke-static {v1, v2}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v1

    new-array v2, v0, [I

    fill-array-data v2, :array_9c0

    const v5, 0x4c423675  # 5.09117E7f

    .line 65
    invoke-static {v2, v5}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v12

    new-array v2, v11, [I

    fill-array-data v2, :array_9dc

    const v5, 0xcdca76f

    invoke-static {v2, v5}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v13

    new-array v2, v4, [J

    fill-array-data v2, :array_9ee

    const v5, 0x4362f87b

    .line 66
    invoke-static {v2, v5, v7}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v14

    new-array v2, v3, [J

    const-wide v15, 0x24790098eb87L

    aput-wide v15, v2, v25

    const v5, 0x78e3f07

    invoke-static {v2, v5, v8}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v15

    const/4 v11, 0x7

    new-array v2, v11, [I

    fill-array-data v2, :array_9fa

    const v5, 0x15c4bf21

    .line 67
    invoke-static {v2, v5}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v16

    new-array v2, v3, [J

    const-wide v17, 0x57f40022c626L

    aput-wide v17, v2, v25

    const v3, 0x4ac23945  # 6364322.5f

    invoke-static {v2, v3, v8}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v17

    const v2, 0x244936e9

    const v3, 0x24380622

    const v5, 0x247c7d38

    const v11, 0x246b4580

    const v4, 0x245ad939

    filled-new-array {v5, v11, v4, v2, v3}, [I

    move-result-object v2

    const v3, 0x7e542438

    .line 68
    invoke-static {v2, v3}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v18

    const/16 v2, 0x8

    new-array v3, v2, [I

    fill-array-data v3, :array_a0c

    const v2, 0x7a4699c0

    invoke-static {v3, v2}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v19

    new-array v2, v6, [I

    fill-array-data v2, :array_a20

    const v3, 0xb204a0

    .line 69
    invoke-static {v2, v3}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v20

    const/16 v2, 0x11

    new-array v2, v2, [J

    fill-array-data v2, :array_a3a

    const v3, 0x6f09852e

    invoke-static {v2, v3, v9}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v21

    move-object v11, v1

    filled-new-array/range {v10 .. v21}, [Ljava/lang/String;

    move-result-object v1

    .line 63
    invoke-static {v1}, Lcom/wukong/manager/WukongInstrumentationHook;->f([Ljava/lang/String;)Ljava/util/LinkedHashMap;

    move-result-object v1

    sput-object v1, Lcom/wukong/manager/WukongInstrumentationHook;->u:Ljava/util/LinkedHashMap;

    const v1, -0x2dbbcffa

    const v2, -0x2dccaf09

    const v3, -0x2d88a0b8

    const v4, -0x2d9966ce

    const v5, -0x2daab307

    .line 71
    filled-new-array {v3, v4, v5, v1, v2}, [I

    move-result-object v1

    const v2, 0x96fd233

    .line 72
    invoke-static {v1, v2}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v9

    new-array v1, v7, [I

    fill-array-data v1, :array_a82

    const v2, 0x1c4cecec

    invoke-static {v1, v2}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v10

    new-array v1, v8, [J

    fill-array-data v1, :array_a92

    const v2, 0x16f7afb

    .line 73
    invoke-static {v1, v2, v0}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v11

    new-array v0, v7, [I

    fill-array-data v0, :array_aa2

    const v1, 0x6f4a8628

    invoke-static {v0, v1}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v12

    const/4 v0, 0x2

    new-array v1, v0, [J

    fill-array-data v1, :array_ab2

    const v2, 0x208f9259

    .line 74
    invoke-static {v1, v2, v7}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v13

    new-array v1, v0, [J

    fill-array-data v1, :array_abe

    const v0, 0x12e5bbdd

    invoke-static {v1, v0, v7}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v14

    const/4 v0, 0x7

    new-array v0, v0, [I

    fill-array-data v0, :array_aca

    const v1, 0x3f33a45f

    .line 75
    invoke-static {v0, v1}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v15

    new-array v0, v7, [I

    fill-array-data v0, :array_adc

    const v1, 0x62380757

    invoke-static {v0, v1}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v16

    const/4 v0, 0x2

    new-array v0, v0, [J

    fill-array-data v0, :array_aec

    const v1, 0x6a20f6d1

    const/4 v5, 0x5

    .line 76
    invoke-static {v0, v1, v5}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v17

    const/16 v2, 0x8

    new-array v0, v2, [I

    fill-array-data v0, :array_af8

    const v1, 0x7d29d480

    invoke-static {v0, v1}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v18

    new-array v0, v6, [I

    fill-array-data v0, :array_b0c

    const v1, 0x5f56d079

    .line 77
    invoke-static {v0, v1}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v19

    const/16 v0, 0x44

    new-array v0, v0, [I

    fill-array-data v0, :array_b26

    const v1, 0x3d2ccc3f

    invoke-static {v0, v1}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v20

    filled-new-array/range {v9 .. v20}, [Ljava/lang/String;

    move-result-object v0

    .line 71
    invoke-static {v0}, Lcom/wukong/manager/WukongInstrumentationHook;->f([Ljava/lang/String;)Ljava/util/LinkedHashMap;

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->v:Ljava/util/LinkedHashMap;

    const-wide/high16 v0, -0x8000000000000000L

    .line 80
    sput-wide v0, Lcom/wukong/manager/WukongInstrumentationHook;->x:J

    .line 87
    new-instance v0, Ljava/util/LinkedHashMap;

    invoke-direct {v0}, Ljava/util/LinkedHashMap;-><init>()V

    sput-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->ae:Ljava/util/LinkedHashMap;

    .line 88
    new-instance v0, Ljava/util/LinkedHashMap;

    invoke-direct {v0}, Ljava/util/LinkedHashMap;-><init>()V

    sput-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->af:Ljava/util/LinkedHashMap;

    return-void

    :array_4ca
    .array-data 4
        -0x624db181
        -0x625e9d90
        -0x626feb2d
        -0x628002fd
        -0x62914a59
        -0x62a29581
        -0x62b3563a
        -0x62c428df
        -0x62d59d12
        -0x62e642a3
        -0x62f76b43
        -0x6308c9ed
        -0x63193eb5
        -0x632ae73c
        -0x633b1d0e
        -0x634c44bb
        -0x635d4e91
        -0x636ee4eb
        -0x637f94df
        -0x6390d3aa
        -0x63a16684
    .end array-data

    :array_4f8
    .array-data 4
        -0x349240a1  # -1.5581023E7f
        -0x34a39c2f  # -1.4443473E7f
        -0x34b41b6e  # -1.3362322E7f
        -0x34c57ebd  # -1.2222787E7f
        -0x34d68f84  # -1.110438E7f
        -0x34e79c8d  # -9986931.0f
        -0x34f875fa  # -8882694.0f
        -0x3509f0b1  # -8062887.5f
        -0x351a74a6  # -7521709.0f
        -0x352bf7f6  # -6947845.0f
        -0x353c1424  # -6419950.0f
        -0x354d0f45  # -5863517.5f
        -0x355e6aec  # -5294730.0f
        -0x356f371f  # -4744304.5f
        -0x3580c87e  # -4181472.5f
        -0x3591e5d4  # -3901067.0f
        -0x35a2f1c3
        -0x35b39c2b
        -0x35c41b64  # -3078439.0f
        -0x35d55679
        -0x35e6eecf
    .end array-data

    :array_526
    .array-data 4
        0x6d94e7cb
        0x6da504b8
        0x6db679b2
        0x6dc70e9b
        0x6dd80bbf
        0x6de9aae1
        0x6dfa96c6
        0x6e0bc65d
        0x6e1c3b0b
        0x6e2d1c61
        0x6e3e6d64
        0x6e4f54e0
        0x6e609b41
        0x6e71d045
        0x6e82e87c
        0x6e933aca
        0x6ea47528
        0x6eb5d73e
    .end array-data

    :array_54e
    .array-data 4
        0x40bd2fed
        0x40ced41a
        0x40df27bc
        0x40f04e4a
        0x4101f265
        0x41127a53
        0x41230175
        0x41345e76
        0x4145c869
        0x4156b43f
        0x416789ea
        0x4178e35a
        0x41896c64
    .end array-data

    :array_56c
    .array-data 4
        -0x368081f1
        -0x36910a6e
        -0x36a2a997
        -0x36b380f5
        -0x36c49c7b
        -0x36d50c9b
        -0x36e6be4b
        -0x36f74e7f
        -0x37082a38  # -507566.25f
        -0x3719d7a7
    .end array-data

    :array_584
    .array-data 8
        0x24585d31a890L
        0x1209051d5c88L
        0x14949d938050L
        0x380c0000001eL
    .end array-data

    :array_598
    .array-data 8
        0x2525a79f4dbbL
        0x70f2a6b6b6f9L
        0x9899c5b8aa8L
        0x6e568e61af3dL
        0x15a1000000feL
    .end array-data

    :array_5b0
    .array-data 8
        0x553be28254eaL
        0x1c76c4b3eaebL
    .end array-data

    :array_5bc
    .array-data 8
        0x48f47df2bd05L
        0x44ca3db33b44L
        0x7412123870bcL
        0x248628242252L
    .end array-data

    :array_5d0
    .array-data 8
        0x21783a6b6612L
        0xf98e43ee5baL
        0x2c1deced51ceL
        0x25fb000000ecL
    .end array-data

    :array_5e4
    .array-data 4
        0x700d240c
        0x6ffc51b0
        0x6feb2621
        0x6fda7eb0
        0x6fc9de98
        0x6fb8b7dc
        0x6fa73a74
        0x6f969fa4
        0x6f85459b
        0x6f74b733
        0x6f63820f
        0x6f52229d
    .end array-data

    :array_600
    .array-data 4
        -0x75705efa
        -0x758135e5
        -0x7592c400
        -0x75a310cb
        -0x75b44793
        -0x75c544c8
        -0x75d6bc76
        -0x75e7d3c7
        -0x75f8bbf9
        -0x7609612a
        -0x761a732c
        -0x762badb0
        -0x763c8c70
        -0x764d4748
        -0x765e1ad5
        -0x766fae8e
        -0x768086b6
        -0x7691e9f3
        -0x76a2c9c4
    .end array-data

    :array_62a
    .array-data 4
        0x6cd18b26
        0x6cc006c6
        0x6caf9a67
        0x6c9eb047
        0x6c8df1ea
        0x6c7cfe6f
        0x6c6b5e9d
        0x6c5a410a
        0x6c49d961
        0x6c380893
        0x6c27c50c
        0x6c16d757
        0x6c05ea2f
        0x6bf4c80e
        0x6be3774d
        0x6bd2e243
        0x6bc168ca
        0x6bb09315
        0x6b9f5831
    .end array-data

    :array_654
    .array-data 4
        0x38990dbb
        0x3888874d
        0x3877f196
        0x38668c97
        0x38554414
        0x3844800b
        0x3833b93a
        0x3822f36b
        0x38113fa1
        0x38006cd8
        0x37efeb21
        0x37de7ce0
        0x37cdf8ea
        0x37bc1627
        0x37abc55e
        0x379aa0a5
        0x37894032
        0x3778c565
        0x3767bcde
        0x3756e4b1
        0x3745ea45
        0x37346aaa
    .end array-data

    :array_684
    .array-data 4
        0x3e6a7a21
        0x3e59871e
        0x3e48ee98
        0x3e376e07
        0x3e266df2
        0x3e15128e
        0x3e048297
        0x3df3dc6c
        0x3de2493a
        0x3dd1f70b
        0x3dc07ffb
        0x3daf7ede
        0x3d9ea8a4
        0x3d8d242f
        0x3d7cadbf
        0x3d6b7ed3
        0x3d5aa478
        0x3d494ddf
        0x3d389b14
        0x3d279b45
        0x3d16d94c
        0x3d055bc2
        0x3cf4f1d6
        0x3ce3b3a9
        0x3cd2b00b
        0x3cc143c5
        0x3cb02979
        0x3c9fcc60
        0x3c8e9bc1
        0x3c7dc53c
        0x3c6c0cde
    .end array-data

    :array_6c6
    .array-data 4
        0x70912d59
        0x708013f0
        0x706fbc69
        0x705e90bd
        0x704d4bfb
        0x703c869d
        0x702b2da2
        0x701ae853
        0x70090f80
        0x6ff83463
        0x6fe702bd
        0x6fd69639
        0x6fc548a1
        0x6fb4f71f
        0x6fa31c4c
        0x6f921981
        0x6f813e86  # 7.9998305E28f
    .end array-data

    :array_6ec
    .array-data 8
        0x672761ea3506L  # 5.60363544729E-310
        0x7dc54a0fac53L
        0x75ca86d41beeL
        0xf47b70811f7L
        0x4ae176b93f20L
        0x1ddfd8b3aa54L
        0x5eb237ed9f47L
        0x15750000d13eL
    .end array-data

    :array_710
    .array-data 4
        -0x5eb90ff1
        -0x5ea813ee
        -0x5e97a5c1
        -0x5e863ac5
        -0x5e7591cf
        -0x5e644e90
        -0x5e533497
        -0x5e42d7e9
        -0x5e311023
        -0x5e20e196
        -0x5e0f96a7
        -0x5dfeb58a
    .end array-data

    :array_72c
    .array-data 4
        -0xe7a29c
        -0xf87aa1
        -0x10992e3
        -0x11a2c34
        -0x12b0c35
        -0x13cbeec
    .end array-data

    :array_73c
    .array-data 4
        -0x10caaa9c
        -0x10b9728d
        -0x10a8a44c
        -0x1097ba2d
        -0x1086cb53
        -0x10753490
        -0x106450cd
    .end array-data

    :array_74e
    .array-data 4
        -0x29512089
        -0x2940249c
        -0x292ffd5d
        -0x291e1ba7
        -0x290d0383
        -0x28fc8028
        -0x28ebf782
        -0x28da6728
        -0x28c9c4db
        -0x28b8e21e
        -0x28a736ba
        -0x289668ad
        -0x288533af
        -0x28749578
        -0x2863d53d
    .end array-data

    :array_770
    .array-data 4
        -0x15d288c9
        -0x15e32478
        -0x15f49cf9
        -0x160550b4
        -0x161633db
        -0x1627fdae
        -0x16387345
        -0x1649f365
        -0x165a60f7
        -0x166b6b80
        -0x167c8b9a
        -0x168d551b
        -0x169eddc9
        -0x16af03e1
        -0x16c07e35
    .end array-data

    :array_792
    .array-data 4
        -0x428885fc
        -0x4277977e
        -0x4266cd79
        -0x4255195e
        -0x42444d40
        -0x42336b10
        -0x42224d37
        -0x4211de06
        -0x4200bd01
        -0x41ef13fc
        -0x41dea2b7
    .end array-data

    :array_7ac
    .array-data 4
        -0x51798125
        -0x516837ef
        -0x51574581
        -0x51465bd3
        -0x5135ec79
        -0x51242699
        -0x51138af2
        -0x510227d8
        -0x50f1a1d6
        -0x50e01531
        -0x50cf6de8
        -0x50be13f6
        -0x50ade6f5
        -0x509cdf06
        -0x508bb7cd
        -0x507a9ef4
        -0x50696c4a
        -0x505810a2
        -0x50473f40
    .end array-data

    :array_7d6
    .array-data 4
        0x39b12fb5
        0x39c253e7
        0x39d38535
        0x39e4272a
        0x39f53e79
        0x3a06df3d
        0x3a1702cc
        0x3a287e58
        0x3a39b820
        0x3a4a7c25
    .end array-data

    :array_7ee
    .array-data 4
        -0x38a1abcf
        -0x389056e1
        -0x387fdf5b
        -0x386eccee
        -0x385dd552
        -0x384c329d
        -0x383beafb
        -0x382aa72b
        -0x38197945
        -0x38088271
        -0x37f78a70  # -139734.25f
        -0x37e682b2
        -0x37d5f7ea
        -0x37c44687
    .end array-data

    :array_80e
    .array-data 4
        0xfe55578
        0xfd40e84
        0xfc3183d
        0xfb2a0bb
        0xfa18fa3
        0xf90e4bc
    .end array-data

    :array_81e
    .array-data 8
        0x1940ad67db91L
        0x486bc1ebecf9L
        0x4b7bf6b8259L
    .end array-data

    :array_82e
    .array-data 8
        0x4860188b7ab3L
        0x2db40000c4e5L
    .end array-data

    :array_83a
    .array-data 4
        0x8871b5a
        0x898f961
        0x8a9fedc
        0x8baa97d
        0x8cbc783
        0x8dc62c3
    .end array-data

    :array_84a
    .array-data 4
        0x3f0737e3
        0x3ef67119
        0x3ee57f5f
        0x3ed4df7f
        0x3ec3c7ea
        0x3eb276ae
    .end array-data

    :array_85a
    .array-data 8
        0x7330467ea02eL
        0x655400dde3e1L
    .end array-data

    :array_866
    .array-data 4
        0x3bcd2eff
        0x3bde859c
        0x3bef73f9
        0x3c008735
        0x3c11f492
        0x3c224311
    .end array-data

    :array_876
    .array-data 4
        -0x689d7421
        -0x688c2899
        -0x687be5f9
        -0x686a7395
        -0x6859559c
        -0x6848e122
        -0x68372435
        -0x6826a7b1
        -0x68158cf0
        -0x68048001
        -0x67f35893
        -0x67e2958e
        -0x67d1e48b
        -0x67c07e60
    .end array-data

    :array_896
    .array-data 4
        -0x262d3ad4
        -0x263ec908
        -0x264fafa7
        -0x2660e7f1
        -0x26716b0d
        -0x2682796d
        -0x26938706
        -0x26a44c17
        -0x26b57b2d
        -0x26c68a12
        -0x26d705d7
    .end array-data

    :array_8b0
    .array-data 4
        -0x19c090d
        -0x18b3c1f
        -0x17a4631
        -0x169b84c
        -0x158b4bc
        -0x14704d2
        -0x1365c8b
        -0x125340c
        -0x114c1bf
        -0x10384ac
        -0xf20c3e
        -0xe1ad04
        -0xd0d13a
        -0xbf0108
        -0xaef6ef
        -0x9db285
        -0x8c2803
        -0x7b2ebf
        -0x6a8262
        -0x59aa52
        -0x48d1ad
        -0x374cce
        -0x267b85
        -0x152af5
        -0x496db
        0xc96fe
        0x1d06b6
        0x2e60d4
        0x3f66db
        0x5008d0
        0x6135cc
        0x722293
        0x83609d
        0x94068d
        0xa57c22
        0xb6ba22
        0xc7edd0
        0xd8243f
        0xe9cfec
        0xfa8409
        0x10b5015
        0x11ce936
        0x12d8819
        0x13ebabf
        0x14f5bd6
        0x160c5b7
        0x17166e0
        0x18286ae
        0x1937079
        0x1a467b3
        0x1b5acb6
        0x1c6a371
        0x1d77d93
        0x1e826c1
        0x1f92500
        0x20a4452
        0x21b40c2
        0x22ce361
        0x23ddd53
        0x24eb300
        0x25ff65d
        0x27044b9
        0x28166c8
        0x292368f
        0x2a346e9
        0x2b4d1d3
    .end array-data

    :array_938
    .array-data 4
        0x63b403e9
        0x63a3f7e8
        0x639206a8
        0x638144aa
        0x63702c41
        0x635fc9c9
        0x634e7a08
        0x633da2d3
        0x632c30fd
        0x631b7e5e
        0x630aef0c
        0x62f9fdcf
        0x62e85b4c
        0x62d79146
        0x62c6a3a2
    .end array-data

    :array_95a
    .array-data 8
        0x5b5a18f112fL
        0x41f1ef5c4604L
        0x2933445dc13fL
    .end array-data

    :array_96a
    .array-data 4
        0x30b2e0af
        0x30c3191e
        0x30d47574
        0x30e56997
        0x30f63c90
        0x31078364
        0x31187837
        0x312954af
        0x313a67b8
        0x314bd952
        0x315cb458
        0x316d2e2a
        0x317eb6d6
        0x318f48c0
    .end array-data

    :array_98a
    .array-data 4
        0xf93558d
        0xf826efe
        0xf71e57b
        0xf606b35  # 1.10647E-29f
        0xf4ff91c
        0xf3ebf7c
        0xf2dd84b
        0xf1c553f
        0xf0bf1f7
        0xefaccb5
    .end array-data

    :array_9a2
    .array-data 8
        0x66b5985478c2L
        0x7bb50000005eL
    .end array-data

    :array_9ae
    .array-data 4
        0x44f31fcc
        0x44e21ab2
        0x44d1feff
        0x44c0200a
        0x44af0619
        0x449ea003  # 1269.0004f
        0x448d0b63
    .end array-data

    :array_9c0
    .array-data 4
        0x3675b67b
        0x36861dd6
        0x3697789c
        0x36a8bf0b
        0x36b95a19
        0x36ca1ede
        0x36dbf444
        0x36ecb695
        0x36fd504c
        0x370eb12c
        0x371f8962
        0x3730ba02
    .end array-data

    :array_9dc
    .array-data 4
        -0x5890de96
        -0x587fc036
        -0x586edffb
        -0x585d8866
        -0x584c91cc
        -0x583b6e1a
        -0x582a03f3
    .end array-data

    :array_9ee
    .array-data 8
        0x3b52d223d5fcL
        0x6207000086dbL
    .end array-data

    :array_9fa
    .array-data 4
        -0x40784b4b
        -0x40899b5c
        -0x409ab1ab
        -0x40aba89c
        -0x40bcbcbf
        -0x40cd5c02
        -0x40de9e31
    .end array-data

    :array_a0c
    .array-data 4
        -0x65c81f01
        -0x65d91b6f
        -0x65ead51f
        -0x65fb6431
        -0x660cf7e6
        -0x661de7fd
        -0x662ece75
        -0x663f5357
    .end array-data

    :array_a20
    .array-data 4
        0x54a4b95
        0x53980f5
        0x528ac5a
        0x5178b2b
        0x5068334
        0x4f5fc50
        0x4e425b0
        0x4d36cca
        0x4c2c213
        0x4b1e1bc
        0x4a07d9b
    .end array-data

    :array_a3a
    .array-data 8
        0x6fb1140be431L
        0x5f1a5076bbd0L
        0x4a574ae84049L
        0x1c712ddd4790L
        0x4db1e0f47aaL
        0x15510225c566L
        0x4e0553aacd67L
        0x46fd047155fbL
        0x4dbc905313dL
        0x545980f33618L
        0x354d0f8e297dL
        0x254cff7961a4L
        0x73a6cfdab148L
        0x45b878122f0aL
        0x6411d64751ecL
        0x2360b0d7c4eaL
        0x1fa20000ef62L
    .end array-data

    :array_a82
    .array-data 4
        -0x12beb7b0
        -0x12cf4adf
        -0x12e0378d
        -0x12f1bdb5
        -0x1302ec8f
        -0x13139f68
    .end array-data

    :array_a92
    .array-data 8
        0x250c790abbb6L
        0x6efe3b9c5359L
        0x393f15f0c43bL
    .end array-data

    :array_aa2
    .array-data 4
        -0x79d77e8a
        -0x79c69a0b
        -0x79b591d3
        -0x79a4bd5f
        -0x799329ee
        -0x7982bdfc
    .end array-data

    :array_ab2
    .array-data 8
        0x38d3129e3091L
        0x2e510000ca6bL
    .end array-data

    :array_abe
    .array-data 8
        0x67acde273050L
        0x43570000c4e7L
    .end array-data

    :array_aca
    .array-data 4
        -0x5b3a6d54
        -0x5b4b7169
        -0x5b5cba8a
        -0x5b6dfeab
        -0x5b7eee58
        -0x5b8f1e2b
        -0x5ba01aec
    .end array-data

    :array_adc
    .array-data 4
        0x7ac9672
        0x79b0a34
        0x78a4816
        0x7798c94
        0x7684143
        0x757e90d
    .end array-data

    :array_aec
    .array-data 8
        0x7610886134ebL
        0x3aa000000076L
    .end array-data

    :array_af8
    .array-data 4
        -0x2b7ff4f5
        -0x2b6ea7b5
        -0x2b5df1d6
        -0x2b4c0952
        -0x2b3ba2ae
        -0x2b2a2ad7
        -0x2b19a697
        -0x2b085c5e
    .end array-data

    :array_b0c
    .array-data 4
        -0x2f862613
        -0x2f757b78
        -0x2f6496b9
        -0x2f53494a
        -0x2f42b0bc
        -0x2f31d182
        -0x2f20220d
        -0x2f0fe85a
        -0x2efe6050
        -0x2eed8047
        -0x2edc5684
    .end array-data

    :array_b26
    .array-data 4
        -0x33c0c760  # -5.012749E7f
        -0x33af0758  # -5.4780576E7f
        -0x339eef5f  # -5.8999428E7f
        -0x338dcfdb  # -6.3488148E7f
        -0x337c8df2  # -6.891531E7f
        -0x336bae6d  # -7.776169E7f
        -0x335adc2c
        -0x33491d0e  # -9.58852E7f
        -0x3338ed78
        -0x33277bc9
        -0x33163bf1
        -0x33057745
        -0x32f4c84c
        -0x32e3c81a
        -0x32d2f700
        -0x32c14d72  # -1.999608E8f
        -0x32b0f3b5
        -0x329f73dd
        -0x328ede31
        -0x327df62f
        -0x326cac63
        -0x325bcff6
        -0x324a3d60  # -3.8117888E8f
        -0x3239dca5
        -0x32287511
        -0x321765f4
        -0x32065992  # -5.2355424E8f
        -0x31f57d85
        -0x31e42a5b
        -0x31d32ac2
        -0x31c28405
        -0x31b17d14
        -0x31a06f67  # -9.376989E8f
        -0x318fe884
        -0x317e2a14
        -0x316d0289
        -0x315cb233
        -0x314b59b3
        -0x313a1ad6
        -0x3129ad54
        -0x311864d1
        -0x31079f57
        -0x30f63850
        -0x30e5fe03
        -0x30d45bd8
        -0x30c3d024
        -0x30b2e68a
        -0x30a1092e
        -0x30902bb6  # -4.0236672E9f
        -0x307f9c6f
        -0x306e6c40
        -0x305d0e8a
        -0x304c7711
        -0x303b8e65
        -0x302a138c  # -7.1780864E9f
        -0x3019f731
        -0x3008c941
        -0x2ff71336
        -0x2fe65a06
        -0x2fd52867
        -0x2fc455b9
        -0x2fb35ffd
        -0x2fa2f19a
        -0x2f91c3c6
        -0x2f80f6a9
        -0x2f6fbc94
        -0x2f5e0822
        -0x2f4ddff0
    .end array-data
.end method

.method public static a(Ljava/lang/String;)Z
    .registers 5

    const/16 v0, 0x1b

    .line 430
    :try_start_2
    new-array v0, v0, [I

    fill-array-data v0, :array_40

    const v1, 0x75c65962

    invoke-static {v0, v1}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v0

    invoke-static {v0}, Ljava/lang/Class;->forName(Ljava/lang/String;)Ljava/lang/Class;

    move-result-object v0

    const/16 v1, 0xa

    new-array v1, v1, [I

    fill-array-data v1, :array_7a

    const v2, 0x208a6191

    .line 431
    invoke-static {v1, v2}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v1

    const-class v2, Ljava/lang/String;

    sget-object v3, Ljava/lang/Boolean;->TYPE:Ljava/lang/Class;

    filled-new-array {v2, v3}, [Ljava/lang/Class;

    move-result-object v2

    invoke-virtual {v0, v1, v2}, Ljava/lang/Class;->getMethod(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;

    move-result-object v0

    .line 432
    sget-object v1, Ljava/lang/Boolean;->FALSE:Ljava/lang/Boolean;

    filled-new-array {p0, v1}, [Ljava/lang/Object;

    move-result-object p0

    const/4 v1, 0x0

    invoke-virtual {v0, v1, p0}, Ljava/lang/reflect/Method;->invoke(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;

    move-result-object p0

    check-cast p0, Ljava/lang/Boolean;

    invoke-virtual {p0}, Ljava/lang/Boolean;->booleanValue()Z

    move-result p0
    :try_end_3d
    .catchall {:try_start_2 .. :try_end_3d} :catchall_3e

    return p0

    :catchall_3e
    const/4 p0, 0x0

    return p0

    :array_40
    .array-data 4
        0x5962f8ea
        0x59735b86
        0x598438b7
        0x59954225
        0x59a665dc
        0x59b7f8ca
        0x59c80e96
        0x59d96f29
        0x59eafedc
        0x59fbc458
        0x5a0c27df
        0x5a1d9713
        0x5a2e5079
        0x5a3f707b
        0x5a5009a1
        0x5a61793c
        0x5a728544
        0x5a835f6a
        0x5a94e0a4
        0x5aa56241
        0x5ab64752
        0x5ac74807
        0x5ad813d9
        0x5ae9d32a
        0x5afa10fe
        0x5b0b5348
        0x5b1ce998
    .end array-data

    :array_7a
    .array-data 4
        0x6191cf63
        0x61a20674
        0x61b3c138
        0x61c40ce2
        0x61d51ae9
        0x61e6a4bc
        0x61f71801
        0x6208b6b9
        0x6219d780
        0x622a7288
    .end array-data
.end method

.method public static b(Ljava/lang/reflect/Field;Ljava/lang/String;)V
    .registers 5

    .line 400
    invoke-virtual {p0}, Ljava/lang/reflect/Field;->getType()Ljava/lang/Class;

    move-result-object v0

    .line 401
    sget-object v1, Ljava/lang/Integer;->TYPE:Ljava/lang/Class;

    invoke-virtual {v1, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v1

    const/4 v2, 0x0

    if-eqz v1, :cond_19

    .line 402
    invoke-virtual {p1}, Ljava/lang/String;->trim()Ljava/lang/String;

    move-result-object p1

    invoke-static {p1}, Ljava/lang/Integer;->parseInt(Ljava/lang/String;)I

    move-result p1

    invoke-virtual {p0, v2, p1}, Ljava/lang/reflect/Field;->setInt(Ljava/lang/Object;I)V

    return-void

    .line 403
    :cond_19
    const-class v1, Ljava/lang/Integer;

    invoke-virtual {v1, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_2d

    .line 404
    invoke-virtual {p1}, Ljava/lang/String;->trim()Ljava/lang/String;

    move-result-object p1

    invoke-static {p1}, Ljava/lang/Integer;->valueOf(Ljava/lang/String;)Ljava/lang/Integer;

    move-result-object p1

    invoke-virtual {p0, v2, p1}, Ljava/lang/reflect/Field;->set(Ljava/lang/Object;Ljava/lang/Object;)V

    return-void

    .line 405
    :cond_2d
    sget-object v1, Ljava/lang/Long;->TYPE:Ljava/lang/Class;

    invoke-virtual {v1, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_41

    .line 406
    invoke-virtual {p1}, Ljava/lang/String;->trim()Ljava/lang/String;

    move-result-object p1

    invoke-static {p1}, Ljava/lang/Long;->parseLong(Ljava/lang/String;)J

    move-result-wide v0

    invoke-virtual {p0, v2, v0, v1}, Ljava/lang/reflect/Field;->setLong(Ljava/lang/Object;J)V

    return-void

    .line 407
    :cond_41
    const-class v1, Ljava/lang/Long;

    invoke-virtual {v1, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_55

    .line 408
    invoke-virtual {p1}, Ljava/lang/String;->trim()Ljava/lang/String;

    move-result-object p1

    invoke-static {p1}, Ljava/lang/Long;->valueOf(Ljava/lang/String;)Ljava/lang/Long;

    move-result-object p1

    invoke-virtual {p0, v2, p1}, Ljava/lang/reflect/Field;->set(Ljava/lang/Object;Ljava/lang/Object;)V

    return-void

    .line 409
    :cond_55
    sget-object v1, Ljava/lang/Boolean;->TYPE:Ljava/lang/Class;

    invoke-virtual {v1, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_69

    .line 410
    invoke-virtual {p1}, Ljava/lang/String;->trim()Ljava/lang/String;

    move-result-object p1

    invoke-static {p1}, Ljava/lang/Boolean;->parseBoolean(Ljava/lang/String;)Z

    move-result p1

    invoke-virtual {p0, v2, p1}, Ljava/lang/reflect/Field;->setBoolean(Ljava/lang/Object;Z)V

    return-void

    .line 411
    :cond_69
    const-class v1, Ljava/lang/Boolean;

    invoke-virtual {v1, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :cond_7d

    .line 412
    invoke-virtual {p1}, Ljava/lang/String;->trim()Ljava/lang/String;

    move-result-object p1

    invoke-static {p1}, Ljava/lang/Boolean;->valueOf(Ljava/lang/String;)Ljava/lang/Boolean;

    move-result-object p1

    invoke-virtual {p0, v2, p1}, Ljava/lang/reflect/Field;->set(Ljava/lang/Object;Ljava/lang/Object;)V

    return-void

    .line 414
    :cond_7d
    invoke-virtual {p0, v2, p1}, Ljava/lang/reflect/Field;->set(Ljava/lang/Object;Ljava/lang/Object;)V

    return-void
.end method

.method public static c(Ljava/lang/String;)Ljava/lang/String;
    .registers 3

    const/4 v0, 0x0

    if-nez p0, :cond_4

    return-object v0

    .line 495
    :cond_4
    invoke-virtual {p0}, Ljava/lang/String;->trim()Ljava/lang/String;

    move-result-object p0

    .line 496
    invoke-virtual {p0}, Ljava/lang/String;->isEmpty()Z

    move-result v1

    if-eqz v1, :cond_f

    return-object v0

    :cond_f
    return-object p0
.end method

.method public static d(Landroid/os/Bundle;J)V
    .registers 15

    .line 203
    sget-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->i:Ljava/lang/String;

    const/4 v1, 0x0

    invoke-virtual {p0, v0, v1}, Landroid/os/BaseBundle;->getBoolean(Ljava/lang/String;Z)Z

    move-result v0

    sput-boolean v0, Lcom/wukong/manager/WukongInstrumentationHook;->y:Z

    .line 204
    sget-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->a:Ljava/lang/String;

    const/4 v2, 0x1

    invoke-virtual {p0, v0, v2}, Landroid/os/BaseBundle;->getBoolean(Ljava/lang/String;Z)Z

    move-result v0

    sput-boolean v0, Lcom/wukong/manager/WukongInstrumentationHook;->z:Z

    .line 205
    sget-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->b:Ljava/lang/String;

    invoke-virtual {p0, v0, v2}, Landroid/os/BaseBundle;->getBoolean(Ljava/lang/String;Z)Z

    move-result v0

    sput-boolean v0, Lcom/wukong/manager/WukongInstrumentationHook;->aa:Z

    .line 206
    sget-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->d:Ljava/lang/String;

    invoke-virtual {p0, v0, v1}, Landroid/os/BaseBundle;->getBoolean(Ljava/lang/String;Z)Z

    move-result v0

    sput-boolean v0, Lcom/wukong/manager/WukongInstrumentationHook;->ab:Z

    .line 207
    sget-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->j:Ljava/lang/String;

    invoke-virtual {p0, v0, v1}, Landroid/os/BaseBundle;->getBoolean(Ljava/lang/String;Z)Z

    move-result v0

    sput-boolean v0, Lcom/wukong/manager/WukongInstrumentationHook;->ac:Z

    .line 208
    sget-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->k:Ljava/lang/String;

    invoke-virtual {p0, v0, v1}, Landroid/os/BaseBundle;->getBoolean(Ljava/lang/String;Z)Z

    move-result v0

    sput-boolean v0, Lcom/wukong/manager/WukongInstrumentationHook;->ad:Z

    .line 210
    sget-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->ae:Ljava/util/LinkedHashMap;

    invoke-virtual {v0}, Ljava/util/LinkedHashMap;->clear()V

    .line 211
    sget-object v3, Lcom/wukong/manager/WukongInstrumentationHook;->c:Ljava/lang/String;

    invoke-virtual {p0, v3}, Landroid/os/Bundle;->getBundle(Ljava/lang/String;)Landroid/os/Bundle;

    move-result-object v3

    .line 212
    sget-object v4, Lcom/wukong/manager/WukongInstrumentationHook;->r:[Ljava/lang/String;

    if-eqz v3, :cond_57

    .line 213
    array-length v5, v4

    move v6, v1

    :goto_43
    if-ge v6, v5, :cond_57

    aget-object v7, v4, v6

    .line 214
    invoke-virtual {v3, v7}, Landroid/os/BaseBundle;->getString(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v8

    invoke-static {v8}, Lcom/wukong/manager/WukongInstrumentationHook;->c(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v8

    if-eqz v8, :cond_54

    .line 216
    invoke-virtual {v0, v7, v8}, Ljava/util/AbstractMap;->put(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;

    :cond_54
    add-int/lit8 v6, v6, 0x1

    goto :goto_43

    .line 220
    :cond_57
    invoke-virtual {v0}, Ljava/util/AbstractMap;->isEmpty()Z

    move-result v3

    if-eqz v3, :cond_62

    .line 221
    sget-object v3, Lcom/wukong/manager/WukongInstrumentationHook;->t:Ljava/util/LinkedHashMap;

    invoke-virtual {v0, v3}, Ljava/util/AbstractMap;->putAll(Ljava/util/Map;)V

    .line 224
    :cond_62
    sget-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->af:Ljava/util/LinkedHashMap;

    invoke-virtual {v0}, Ljava/util/LinkedHashMap;->clear()V

    .line 225
    sget-object v3, Lcom/wukong/manager/WukongInstrumentationHook;->l:Ljava/lang/String;

    invoke-virtual {p0, v3}, Landroid/os/Bundle;->getBundle(Ljava/lang/String;)Landroid/os/Bundle;

    move-result-object p0

    if-eqz p0, :cond_b6

    .line 227
    invoke-virtual {p0}, Landroid/os/BaseBundle;->keySet()Ljava/util/Set;

    move-result-object v3

    invoke-interface {v3}, Ljava/util/Set;->iterator()Ljava/util/Iterator;

    move-result-object v3

    :cond_77
    :goto_77
    invoke-interface {v3}, Ljava/util/Iterator;->hasNext()Z

    move-result v5

    if-eqz v5, :cond_b6

    invoke-interface {v3}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v5

    check-cast v5, Ljava/lang/String;

    .line 228
    invoke-static {v5}, Lcom/wukong/manager/WukongInstrumentationHook;->c(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v6

    .line 229
    invoke-virtual {p0, v5}, Landroid/os/Bundle;->getBundle(Ljava/lang/String;)Landroid/os/Bundle;

    move-result-object v5

    .line 330
    new-instance v7, Ljava/util/LinkedHashMap;

    invoke-direct {v7}, Ljava/util/LinkedHashMap;-><init>()V

    if-nez v5, :cond_93

    goto :goto_a9

    .line 334
    :cond_93
    array-length v8, v4

    move v9, v1

    :goto_95
    if-ge v9, v8, :cond_a9

    aget-object v10, v4, v9

    .line 335
    invoke-virtual {v5, v10}, Landroid/os/BaseBundle;->getString(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v11

    invoke-static {v11}, Lcom/wukong/manager/WukongInstrumentationHook;->c(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v11

    if-eqz v11, :cond_a6

    .line 337
    invoke-virtual {v7, v10, v11}, Ljava/util/AbstractMap;->put(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;

    :cond_a6
    add-int/lit8 v9, v9, 0x1

    goto :goto_95

    :cond_a9
    :goto_a9
    if-eqz v6, :cond_77

    .line 231
    invoke-virtual {v7}, Ljava/util/AbstractMap;->isEmpty()Z

    move-result v5

    if-eqz v5, :cond_b2

    goto :goto_77

    .line 234
    :cond_b2
    invoke-virtual {v0, v6, v7}, Ljava/util/AbstractMap;->put(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;

    goto :goto_77

    .line 238
    :cond_b6
    sput-wide p1, Lcom/wukong/manager/WukongInstrumentationHook;->x:J

    .line 239
    sput-boolean v2, Lcom/wukong/manager/WukongInstrumentationHook;->w:Z

    return-void
.end method

.method public static e(Ljava/util/LinkedHashMap;)V
    .registers 9

    if-eqz p0, :cond_135

    .line 352
    invoke-interface {p0}, Ljava/util/Map;->isEmpty()Z

    move-result v0

    if-eqz v0, :cond_a

    goto/16 :goto_135

    .line 355
    :cond_a
    invoke-interface {p0}, Ljava/util/Map;->entrySet()Ljava/util/Set;

    move-result-object p0

    invoke-interface {p0}, Ljava/util/Set;->iterator()Ljava/util/Iterator;

    move-result-object p0

    :cond_12
    :goto_12
    invoke-interface {p0}, Ljava/util/Iterator;->hasNext()Z

    move-result v0

    if-eqz v0, :cond_135

    invoke-interface {p0}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Ljava/util/Map$Entry;

    .line 356
    invoke-interface {v0}, Ljava/util/Map$Entry;->getKey()Ljava/lang/Object;

    move-result-object v1

    check-cast v1, Ljava/lang/String;

    invoke-interface {v0}, Ljava/util/Map$Entry;->getValue()Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Ljava/lang/String;

    .line 361
    invoke-static {v1}, Landroid/text/TextUtils;->isEmpty(Ljava/lang/CharSequence;)Z

    move-result v2

    if-nez v2, :cond_12

    if-nez v0, :cond_33

    goto :goto_12

    .line 378
    :cond_33
    invoke-static {v1}, Lcom/wukong/manager/WukongInstrumentationHook;->c(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v2

    const/4 v3, 0x0

    if-nez v2, :cond_3c

    goto/16 :goto_f8

    :cond_3c
    const/16 v4, 0xa

    .line 382
    new-array v4, v4, [I

    fill-array-data v4, :array_136

    const v5, 0x161dbd1a

    invoke-static {v4, v5}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v4

    invoke-virtual {v4, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v4

    if-eqz v4, :cond_52

    goto/16 :goto_f8

    :cond_52
    const/16 v4, 0x8

    .line 385
    new-array v5, v4, [I

    fill-array-data v5, :array_14e

    const v6, 0x33d7a974

    invoke-static {v5, v6}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v5

    invoke-virtual {v2, v5}, Ljava/lang/String;->startsWith(Ljava/lang/String;)Z

    move-result v5

    const-class v6, Landroid/os/Build$VERSION;

    if-eqz v5, :cond_8b

    const/4 v5, 0x2

    .line 386
    new-array v5, v5, [J

    fill-array-data v5, :array_162

    const v7, 0x570ba9a7

    invoke-static {v5, v7, v4}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v4

    invoke-virtual {v4}, Ljava/lang/String;->length()I

    move-result v4

    invoke-virtual {v2, v4}, Ljava/lang/String;->substring(I)Ljava/lang/String;

    move-result-object v2

    invoke-static {v2}, Lcom/wukong/manager/WukongInstrumentationHook;->c(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v2

    if-nez v2, :cond_85

    goto/16 :goto_f8

    .line 387
    :cond_85
    new-instance v3, Lcom/wukong/manager/cx;

    invoke-direct {v3, v6, v2}, Lcom/wukong/manager/cx;-><init>(Ljava/lang/Class;Ljava/lang/String;)V

    goto :goto_f8

    :cond_8b
    const/16 v3, 0xe

    .line 389
    new-array v3, v3, [I

    fill-array-data v3, :array_16e

    const v5, 0x47aa1b2c

    invoke-static {v3, v5}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v3

    invoke-virtual {v3, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v3

    if-nez v3, :cond_f3

    const/4 v3, 0x7

    new-array v5, v3, [I

    fill-array-data v5, :array_18e

    const v7, 0x451cd527

    .line 390
    invoke-static {v5, v7}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v5

    invoke-virtual {v5, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v5

    if-nez v5, :cond_f3

    new-array v3, v3, [I

    fill-array-data v3, :array_1a0

    const v5, 0x7ff9c134

    .line 391
    invoke-static {v3, v5}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v3

    invoke-virtual {v3, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v3

    if-nez v3, :cond_f3

    const/16 v3, 0xb

    new-array v3, v3, [I

    fill-array-data v3, :array_1b2

    const v5, 0x2ed08b3c

    .line 392
    invoke-static {v3, v5}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v3

    invoke-virtual {v3, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v3

    if-nez v3, :cond_f3

    new-array v3, v4, [I

    fill-array-data v3, :array_1cc

    const v4, 0x6746e8

    .line 393
    invoke-static {v3, v4}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v3

    invoke-virtual {v3, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v3

    if-eqz v3, :cond_eb

    goto :goto_f3

    .line 396
    :cond_eb
    new-instance v3, Lcom/wukong/manager/cx;

    const-class v4, Landroid/os/Build;

    invoke-direct {v3, v4, v2}, Lcom/wukong/manager/cx;-><init>(Ljava/lang/Class;Ljava/lang/String;)V

    goto :goto_f8

    .line 394
    :cond_f3
    :goto_f3
    new-instance v3, Lcom/wukong/manager/cx;

    invoke-direct {v3, v6, v2}, Lcom/wukong/manager/cx;-><init>(Ljava/lang/Class;Ljava/lang/String;)V

    :goto_f8
    if-nez v3, :cond_fc

    goto/16 :goto_12

    .line 369
    :cond_fc
    :try_start_fc
    iget-object v2, v3, Lcom/wukong/manager/cx;->f:Ljava/io/Serializable;

    check-cast v2, Ljava/lang/Class;

    iget-object v3, v3, Lcom/wukong/manager/cx;->e:Ljava/lang/String;

    invoke-virtual {v2, v3}, Ljava/lang/Class;->getDeclaredField(Ljava/lang/String;)Ljava/lang/reflect/Field;

    move-result-object v2

    const/4 v3, 0x1

    .line 370
    invoke-virtual {v2, v3}, Ljava/lang/reflect/AccessibleObject;->setAccessible(Z)V

    .line 371
    invoke-static {v2, v0}, Lcom/wukong/manager/WukongInstrumentationHook;->b(Ljava/lang/reflect/Field;Ljava/lang/String;)V
    :try_end_10d
    .catchall {:try_start_fc .. :try_end_10d} :catchall_10f

    goto/16 :goto_12

    :catchall_10f
    move-exception v0

    .line 373
    new-instance v2, Ljava/lang/StringBuilder;

    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V

    const/4 v3, 0x5

    new-array v3, v3, [J

    fill-array-data v3, :array_1e0

    const v4, 0x787878b0

    const/16 v5, 0x13

    invoke-static {v3, v4, v5}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v3

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v1

    sget-object v2, Lcom/wukong/manager/WukongInstrumentationHook;->e:Ljava/lang/String;

    invoke-static {v2, v1, v0}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I

    goto/16 :goto_12

    :cond_135
    :goto_135
    return-void

    :array_136
    .array-data 4
        -0x42e5edc5
        -0x42d439bb
        -0x42c3dcf8
        -0x42b21367
        -0x42a1663b
        -0x4290e6a3
        -0x427f10f2
        -0x426e69c8
        -0x425d1f57
        -0x424cd331
    .end array-data

    :array_14e
    .array-data 4
        -0x568bb5e4
        -0x567ab3ef
        -0x56690887
        -0x56581fc3
        -0x5647dbbb
        -0x5636cca5
        -0x56257583
        -0x5614cddf
    .end array-data

    :array_162
    .array-data 8
        0x46dee7f5c673L
        0x7c5831e634d0L
    .end array-data

    :array_16e
    .array-data 4
        0x1c092194
        0x1bf8b6a8
        0x1be7f726
        0x1bd66ecc
        0x1bc53dff
        0x1bb44dc1
        0x1ba3608e
        0x1b928444
        0x1b8178c3
        0x1b70a700
        0x1b5f2929
        0x1b4e23ff
        0x1b3d024d
        0x1b2c8fd9
    .end array-data

    :array_18e
    .array-data 4
        -0x2ad88452
        -0x2ac7978c
        -0x2ab660bf
        -0x2aa5c8c9
        -0x2a945982
        -0x2a83c94d
        -0x2a72693e
    .end array-data

    :array_1a0
    .array-data 4
        -0x3ecbf943
        -0x3ebaf400
        -0x3ea9068c
        -0x3e987524
        -0x3e879483
        -0x3e76c6b5
        -0x3e65d51e
    .end array-data

    :array_1b2
    .array-data 4
        -0x74190967
        -0x742ac509
        -0x743b625f
        -0x744c8df0
        -0x745d11e3
        -0x746ee467
        -0x747f2872
        -0x74903a9a
        -0x74a12dc5
        -0x74b2af2b
        -0x74c348c8
    .end array-data

    :array_1cc
    .array-data 4
        0x46e8faea
        0x46f9a7c8
        0x470aa06f
        0x471b2b9b
        0x472c260a
        0x473d59d9
        0x474e5873
        0x475f19ae
    .end array-data

    :array_1e0
    .array-data 8
        0x47bb69eb1b1dL
        0x70ace79bff09L
        0x1bcf8b178d34L
        0x1c350fb3f630L
        0x4b5100c0df38L
    .end array-data
.end method

.method public static varargs f([Ljava/lang/String;)Ljava/util/LinkedHashMap;
    .registers 5

    .line 344
    new-instance v0, Ljava/util/LinkedHashMap;

    invoke-direct {v0}, Ljava/util/LinkedHashMap;-><init>()V

    const/4 v1, 0x0

    :goto_6
    add-int/lit8 v2, v1, 0x1

    .line 345
    array-length v3, p0

    if-ge v2, v3, :cond_15

    .line 346
    aget-object v3, p0, v1

    aget-object v2, p0, v2

    invoke-virtual {v0, v3, v2}, Ljava/util/AbstractMap;->put(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;

    add-int/lit8 v1, v1, 0x2

    goto :goto_6

    :cond_15
    return-object v0
.end method

.method public static g(Landroid/content/Context;)V
    .registers 6

    const/16 v0, 0x12

    .line 173
    new-array v0, v0, [I

    fill-array-data v0, :array_ac

    const v1, 0xf4071d9

    invoke-static {v0, v1}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v0

    invoke-static {v0}, Lcom/wukong/manager/WukongInstrumentationHook;->a(Ljava/lang/String;)Z

    move-result v0

    if-nez v0, :cond_2a

    const/16 v0, 0x10

    new-array v0, v0, [I

    fill-array-data v0, :array_d4

    const v1, 0x298256ea

    .line 174
    invoke-static {v0, v1}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v0

    invoke-static {v0}, Lcom/wukong/manager/WukongInstrumentationHook;->a(Ljava/lang/String;)Z

    move-result v0

    if-nez v0, :cond_2a

    goto/16 :goto_9b

    .line 178
    :cond_2a
    :try_start_2a
    invoke-virtual {p0}, Landroid/content/Context;->getPackageManager()Landroid/content/pm/PackageManager;

    move-result-object v0

    sget-object v1, Lcom/wukong/manager/WukongInstrumentationHook;->f:Ljava/lang/String;

    const/4 v2, 0x0

    invoke-virtual {v0, v1, v2}, Landroid/content/pm/PackageManager;->resolveContentProvider(Ljava/lang/String;I)Landroid/content/pm/ProviderInfo;

    move-result-object v0
    :try_end_35
    .catchall {:try_start_2a .. :try_end_35} :catchall_9b

    if-eqz v0, :cond_9b

    const/4 v0, 0x0

    .line 186
    :try_start_38
    invoke-virtual {p0}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object p0

    new-instance v2, Ljava/lang/StringBuilder;

    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V

    const/16 v3, 0xa

    new-array v3, v3, [I

    fill-array-data v3, :array_f8

    const v4, 0xa93b329

    .line 187
    invoke-static {v3, v4}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v3

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v1

    invoke-static {v1}, Landroid/net/Uri;->parse(Ljava/lang/String;)Landroid/net/Uri;

    move-result-object v1

    sget-object v2, Lcom/wukong/manager/WukongInstrumentationHook;->g:Ljava/lang/String;

    .line 186
    invoke-virtual {p0, v1, v2, v0, v0}, Landroid/content/ContentResolver;->call(Landroid/net/Uri;Ljava/lang/String;Ljava/lang/String;Landroid/os/Bundle;)Landroid/os/Bundle;

    move-result-object v0
    :try_end_63
    .catch Ljava/lang/IllegalArgumentException; {:try_start_38 .. :try_end_63} :catch_7a
    .catch Ljava/lang/IllegalStateException; {:try_start_38 .. :try_end_63} :catch_7a
    .catchall {:try_start_38 .. :try_end_63} :catchall_64

    goto :goto_7a

    :catchall_64
    move-exception p0

    .line 197
    sget-object v1, Lcom/wukong/manager/WukongInstrumentationHook;->e:Ljava/lang/String;

    const/16 v2, 0xb

    new-array v2, v2, [J

    fill-array-data v2, :array_110

    const v3, 0x6c85ce34

    const/16 v4, 0x2a

    invoke-static {v2, v3, v4}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v2

    invoke-static {v1, v2, p0}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I

    :catch_7a
    :goto_7a
    if-eqz v0, :cond_9b

    .line 156
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->h:Ljava/lang/String;

    const-wide/high16 v1, -0x8000000000000000L

    invoke-virtual {v0, p0, v1, v2}, Landroid/os/BaseBundle;->getLong(Ljava/lang/String;J)J

    move-result-wide v1

    .line 157
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->s:Ljava/lang/Object;

    monitor-enter p0

    .line 158
    :try_start_87
    sget-boolean v3, Lcom/wukong/manager/WukongInstrumentationHook;->w:Z

    if-eqz v3, :cond_94

    sget-wide v3, Lcom/wukong/manager/WukongInstrumentationHook;->x:J

    cmp-long v3, v1, v3

    if-eqz v3, :cond_97

    goto :goto_94

    :catchall_92
    move-exception v0

    goto :goto_99

    .line 159
    :cond_94
    :goto_94
    invoke-static {v0, v1, v2}, Lcom/wukong/manager/WukongInstrumentationHook;->d(Landroid/os/Bundle;J)V

    .line 161
    :cond_97
    monitor-exit p0

    goto :goto_a9

    :goto_99
    monitor-exit p0
    :try_end_9a
    .catchall {:try_start_87 .. :try_end_9a} :catchall_92

    throw v0

    .line 165
    :catchall_9b
    :cond_9b
    :goto_9b
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->s:Ljava/lang/Object;

    monitor-enter p0

    .line 166
    :try_start_9e
    sget-boolean v0, Lcom/wukong/manager/WukongInstrumentationHook;->w:Z

    if-nez v0, :cond_a8

    .line 167
    invoke-static {}, Lcom/wukong/manager/WukongInstrumentationHook;->i()V

    goto :goto_a8

    :catchall_a6
    move-exception v0

    goto :goto_aa

    .line 169
    :cond_a8
    :goto_a8
    monitor-exit p0

    :goto_a9
    return-void

    :goto_aa
    monitor-exit p0
    :try_end_ab
    .catchall {:try_start_9e .. :try_end_ab} :catchall_a6

    throw v0

    :array_ac
    .array-data 4
        0x72fab32e
        0x72e975d3
        0x72d85996
        0x72c79963
        0x72b61e6f
        0x72a5f8c6
        0x72942a7d
        0x72834ed9
        0x727276f8
        0x7261bfb1
        0x72509a66
        0x723f30ab
        0x722eb2d8
        0x721d95f3
        0x720c5fb1
        0x71fb679d
        0x71eae70d
        0x71d958b7
    .end array-data

    :array_d4
    .array-data 4
        0x56eaa7df
        0x56fbf8f3
        0x570c3e16
        0x571de770
        0x572e127b
        0x573f7cce
        0x5750ade9
        0x57616563
        0x577247f1  # 2.663908E14f
        0x57839f76
        0x579458a0
        0x57a56de3
        0x57b6facd
        0x57c7e404
        0x57d862bc
        0x57e9b229
    .end array-data

    :array_f8
    .array-data 4
        -0x4c3dc9e2
        -0x4c4eacba
        -0x4c5fcb75
        -0x4c700951
        -0x4c81a84c
        -0x4c92093b
        -0x4ca3f0e5
        -0x4cb49423
        -0x4cc5f839
        -0x4cd63782
    .end array-data

    :array_110
    .array-data 8
        0xaba8e9fd543L
        0x748bf7d2c057L
        0x1126fb4737a5L
        0x75e1c3e17f78L
        0x24e69dc12b18L
        0x5d4ad7d2637bL
        0x1bb94ac1445fL
        0x3871b04be796L
        0x43e109a61e8aL  # 3.6874000839809E-310
        0x50f81a5fc561L
        0x25da0000655bL
    .end array-data
.end method

.method public static h(Ljava/lang/String;)Ljava/util/LinkedHashMap;
    .registers 3

    .line 323
    sget-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->s:Ljava/lang/Object;

    monitor-enter v0

    .line 324
    :try_start_3
    sget-object v1, Lcom/wukong/manager/WukongInstrumentationHook;->af:Ljava/util/LinkedHashMap;

    invoke-virtual {v1, p0}, Ljava/util/LinkedHashMap;->get(Ljava/lang/Object;)Ljava/lang/Object;

    move-result-object p0

    check-cast p0, Ljava/util/LinkedHashMap;

    if-nez p0, :cond_15

    .line 325
    new-instance p0, Ljava/util/LinkedHashMap;

    invoke-direct {p0}, Ljava/util/LinkedHashMap;-><init>()V

    goto :goto_1b

    :catchall_13
    move-exception p0

    goto :goto_1d

    :cond_15
    new-instance v1, Ljava/util/LinkedHashMap;

    invoke-direct {v1, p0}, Ljava/util/LinkedHashMap;-><init>(Ljava/util/Map;)V

    move-object p0, v1

    :goto_1b
    monitor-exit v0

    return-object p0

    .line 326
    :goto_1d
    monitor-exit v0
    :try_end_1e
    .catchall {:try_start_3 .. :try_end_1e} :catchall_13

    throw p0
.end method

.method public static i()V
    .registers 4

    const/4 v0, 0x0

    .line 243
    sput-boolean v0, Lcom/wukong/manager/WukongInstrumentationHook;->y:Z

    const/4 v1, 0x1

    .line 244
    sput-boolean v1, Lcom/wukong/manager/WukongInstrumentationHook;->z:Z

    .line 245
    sput-boolean v1, Lcom/wukong/manager/WukongInstrumentationHook;->aa:Z

    .line 246
    sput-boolean v0, Lcom/wukong/manager/WukongInstrumentationHook;->ab:Z

    .line 247
    sput-boolean v0, Lcom/wukong/manager/WukongInstrumentationHook;->ac:Z

    .line 248
    sput-boolean v0, Lcom/wukong/manager/WukongInstrumentationHook;->ad:Z

    .line 249
    sget-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->ae:Ljava/util/LinkedHashMap;

    invoke-virtual {v0}, Ljava/util/LinkedHashMap;->clear()V

    .line 250
    sget-object v2, Lcom/wukong/manager/WukongInstrumentationHook;->t:Ljava/util/LinkedHashMap;

    invoke-virtual {v0, v2}, Ljava/util/AbstractMap;->putAll(Ljava/util/Map;)V

    .line 251
    sget-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->af:Ljava/util/LinkedHashMap;

    invoke-virtual {v0}, Ljava/util/LinkedHashMap;->clear()V

    const-wide v2, -0x7fffffffffffffffL  # -4.9E-324

    .line 252
    sput-wide v2, Lcom/wukong/manager/WukongInstrumentationHook;->x:J

    .line 253
    sput-boolean v1, Lcom/wukong/manager/WukongInstrumentationHook;->w:Z

    return-void
.end method

.method public static isPhotosEnabledForCurrentProcess()Z
    .registers 2

    const/4 v0, 0x0

    const v1, 0x7213cd6c

    .line 509
    invoke-static {v1, v0}, Lcom/wukong/manager/cy;->h(ILjava/lang/Object;)I

    move-result v0

    .line 510
    invoke-static {v0, v1}, Lcom/wukong/manager/cy;->i(II)Z

    move-result v0

    if-eqz v0, :cond_13

    .line 511
    invoke-static {}, Lcom/wukong/manager/WukongInstrumentationHook;->k()Z

    move-result v0

    return v0

    :cond_13
    const/4 v0, 0x0

    return v0
.end method

.method private static j(Landroid/content/Context;)V
    .registers 8

    const v0, 0x2ac95dad

    const/4 v1, 0x0

    .line 95
    invoke-static {v0, v1}, Lcom/wukong/manager/cy;->h(ILjava/lang/Object;)I

    if-nez p0, :cond_b

    goto/16 :goto_25e

    .line 464
    :cond_b
    :try_start_b
    invoke-virtual {p0}, Landroid/content/Context;->getPackageName()Ljava/lang/String;

    move-result-object v0
    :try_end_f
    .catchall {:try_start_b .. :try_end_f} :catchall_10

    goto :goto_11

    :catchall_10
    move-object v0, v1

    .line 100
    :goto_11
    invoke-static {v0}, Landroid/text/TextUtils;->isEmpty(Ljava/lang/CharSequence;)Z

    move-result v2

    if-eqz v2, :cond_19

    goto/16 :goto_25e

    :cond_19
    const/16 v2, 0x1a

    const/16 v3, 0x17

    .line 472
    :try_start_1d
    new-array v2, v2, [I

    fill-array-data v2, :array_260

    const v4, 0x661e1e4e

    invoke-static {v2, v4}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v2

    invoke-static {v2}, Ljava/lang/Class;->forName(Ljava/lang/String;)Ljava/lang/Class;

    move-result-object v2

    const/16 v4, 0x12

    new-array v4, v4, [I

    fill-array-data v4, :array_298

    const v5, 0x1b8ad7c6

    .line 473
    invoke-static {v4, v5}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v4

    invoke-virtual {v2, v4, v1}, Ljava/lang/Class;->getDeclaredMethod(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;

    move-result-object v2

    .line 474
    invoke-virtual {v2, v1, v1}, Ljava/lang/reflect/Method;->invoke(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;

    move-result-object v2

    .line 475
    instance-of v4, v2, Ljava/lang/String;

    if-eqz v4, :cond_4b

    .line 476
    check-cast v2, Ljava/lang/String;
    :try_end_49
    .catchall {:try_start_1d .. :try_end_49} :catchall_4b

    :goto_49
    move-object v1, v2

    goto :goto_79

    .line 482
    :catchall_4b
    :cond_4b
    :try_start_4b
    new-array v2, v3, [I

    fill-array-data v2, :array_2c0

    const v4, 0x41837fc3

    invoke-static {v2, v4}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v2

    invoke-static {v2}, Ljava/lang/Class;->forName(Ljava/lang/String;)Ljava/lang/Class;

    move-result-object v2

    const/4 v4, 0x4

    new-array v4, v4, [J

    fill-array-data v4, :array_2f2

    const v5, 0x4d58d3fd  # 2.2736072E8f

    const/16 v6, 0xe

    .line 483
    invoke-static {v4, v5, v6}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v4

    invoke-virtual {v2, v4, v1}, Ljava/lang/Class;->getDeclaredMethod(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;

    move-result-object v2

    .line 484
    invoke-virtual {v2, v1, v1}, Ljava/lang/reflect/Method;->invoke(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;

    move-result-object v2

    .line 485
    instance-of v4, v2, Ljava/lang/String;

    if-eqz v4, :cond_79

    check-cast v2, Ljava/lang/String;
    :try_end_78
    .catchall {:try_start_4b .. :try_end_78} :catchall_79

    goto :goto_49

    .line 439
    :catchall_79
    :cond_79
    :goto_79
    sget-object v2, Lcom/wukong/manager/WukongInstrumentationHook;->m:Ljava/lang/String;

    invoke-virtual {v2, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v2

    const/4 v4, 0x1

    const/4 v5, 0x0

    if-nez v2, :cond_a7

    .line 446
    sget-object v2, Lcom/wukong/manager/WukongInstrumentationHook;->n:Ljava/lang/String;

    invoke-virtual {v2, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v2

    if-eqz v2, :cond_94

    sget-object v2, Lcom/wukong/manager/WukongInstrumentationHook;->o:Ljava/lang/String;

    invoke-virtual {v2, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v2

    if-eqz v2, :cond_94

    goto :goto_a7

    .line 440
    :cond_94
    sget-object v2, Lcom/wukong/manager/WukongInstrumentationHook;->p:Ljava/lang/String;

    .line 441
    invoke-virtual {v2, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v2

    if-nez v2, :cond_a7

    sget-object v2, Lcom/wukong/manager/WukongInstrumentationHook;->q:Ljava/lang/String;

    .line 442
    invoke-virtual {v2, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v2

    if-eqz v2, :cond_a5

    goto :goto_a7

    :cond_a5
    move v2, v5

    goto :goto_a8

    :cond_a7
    :goto_a7
    move v2, v4

    .line 451
    :goto_a8
    :try_start_a8
    invoke-virtual {p0}, Landroid/content/Context;->getApplicationInfo()Landroid/content/pm/ApplicationInfo;

    move-result-object v6

    if-eqz v6, :cond_b6

    .line 452
    iget v6, v6, Landroid/content/pm/ApplicationInfo;->flags:I
    :try_end_b0
    .catchall {:try_start_a8 .. :try_end_b0} :catchall_b4

    and-int/lit16 v6, v6, 0x81

    if-eqz v6, :cond_b6

    :catchall_b4
    move v6, v5

    goto :goto_b7

    :cond_b6
    move v6, v4

    :goto_b7
    if-nez v2, :cond_bd

    if-nez v6, :cond_bd

    goto/16 :goto_25e

    .line 110
    :cond_bd
    :try_start_bd
    invoke-static {p0}, Lcom/wukong/manager/WukongInstrumentationHook;->g(Landroid/content/Context;)V

    .line 111
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->m:Ljava/lang/String;

    invoke-virtual {p0, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result p0

    if-eqz p0, :cond_112

    .line 263
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->s:Ljava/lang/Object;

    monitor-enter p0
    :try_end_cb
    .catchall {:try_start_bd .. :try_end_cb} :catchall_10a

    .line 264
    :try_start_cb
    sget-boolean v1, Lcom/wukong/manager/WukongInstrumentationHook;->y:Z

    if-eqz v1, :cond_d6

    sget-boolean v1, Lcom/wukong/manager/WukongInstrumentationHook;->aa:Z

    if-eqz v1, :cond_d6

    goto :goto_d7

    :catchall_d4
    move-exception v1

    goto :goto_110

    :cond_d6
    move v4, v5

    :goto_d7
    monitor-exit p0
    :try_end_d8
    .catchall {:try_start_cb .. :try_end_d8} :catchall_d4

    if-eqz v4, :cond_25e

    .line 317
    :try_start_da
    monitor-enter p0
    :try_end_db
    .catchall {:try_start_da .. :try_end_db} :catchall_10a

    .line 318
    :try_start_db
    new-instance v1, Ljava/util/LinkedHashMap;

    sget-object v2, Lcom/wukong/manager/WukongInstrumentationHook;->ae:Ljava/util/LinkedHashMap;

    invoke-direct {v1, v2}, Ljava/util/LinkedHashMap;-><init>(Ljava/util/Map;)V

    monitor-exit p0
    :try_end_e3
    .catchall {:try_start_db .. :try_end_e3} :catchall_10d

    .line 113
    :try_start_e3
    invoke-static {v1}, Lcom/wukong/manager/WukongInstrumentationHook;->e(Ljava/util/LinkedHashMap;)V

    .line 114
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->e:Ljava/lang/String;

    new-instance v1, Ljava/lang/StringBuilder;

    invoke-direct {v1}, Ljava/lang/StringBuilder;-><init>()V

    const/16 v2, 0x21

    new-array v2, v2, [I

    fill-array-data v2, :array_306

    const v3, 0x3057ee58

    invoke-static {v2, v3}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v1, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v1

    invoke-static {p0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I
    :try_end_108
    .catchall {:try_start_e3 .. :try_end_108} :catchall_10a

    goto/16 :goto_25e

    :catchall_10a
    move-exception p0

    goto/16 :goto_23a

    :catchall_10d
    move-exception v1

    .line 319
    :try_start_10e
    monitor-exit p0
    :try_end_10f
    .catchall {:try_start_10e .. :try_end_10f} :catchall_10d

    :try_start_10f
    throw v1
    :try_end_110
    .catchall {:try_start_10f .. :try_end_110} :catchall_10a

    .line 265
    :goto_110
    :try_start_110
    monitor-exit p0
    :try_end_111
    .catchall {:try_start_110 .. :try_end_111} :catchall_d4

    :try_start_111
    throw v1

    .line 446
    :cond_112
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->n:Ljava/lang/String;

    invoke-virtual {p0, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result p0

    if-eqz p0, :cond_124

    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->o:Ljava/lang/String;

    invoke-virtual {p0, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result p0

    if-eqz p0, :cond_124

    move p0, v4

    goto :goto_125

    :cond_124
    move p0, v5

    :goto_125
    if-eqz p0, :cond_16e

    .line 257
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->s:Ljava/lang/Object;

    monitor-enter p0
    :try_end_12a
    .catchall {:try_start_111 .. :try_end_12a} :catchall_10a

    .line 258
    :try_start_12a
    sget-boolean v2, Lcom/wukong/manager/WukongInstrumentationHook;->y:Z

    if-eqz v2, :cond_135

    sget-boolean v2, Lcom/wukong/manager/WukongInstrumentationHook;->z:Z

    if-eqz v2, :cond_135

    goto :goto_136

    :catchall_133
    move-exception v1

    goto :goto_16c

    :cond_135
    move v4, v5

    :goto_136
    monitor-exit p0
    :try_end_137
    .catchall {:try_start_12a .. :try_end_137} :catchall_133

    if-eqz v4, :cond_25e

    .line 317
    :try_start_139
    monitor-enter p0
    :try_end_13a
    .catchall {:try_start_139 .. :try_end_13a} :catchall_10a

    .line 318
    :try_start_13a
    new-instance v2, Ljava/util/LinkedHashMap;

    sget-object v3, Lcom/wukong/manager/WukongInstrumentationHook;->ae:Ljava/util/LinkedHashMap;

    invoke-direct {v2, v3}, Ljava/util/LinkedHashMap;-><init>(Ljava/util/Map;)V

    monitor-exit p0
    :try_end_142
    .catchall {:try_start_13a .. :try_end_142} :catchall_169

    .line 120
    :try_start_142
    invoke-static {v2}, Lcom/wukong/manager/WukongInstrumentationHook;->e(Ljava/util/LinkedHashMap;)V

    .line 121
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->e:Ljava/lang/String;

    new-instance v2, Ljava/lang/StringBuilder;

    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V

    const/16 v3, 0x23

    new-array v3, v3, [I

    fill-array-data v3, :array_34c

    const v4, 0x6563806a

    invoke-static {v3, v4}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v3

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v1

    invoke-static {p0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I
    :try_end_167
    .catchall {:try_start_142 .. :try_end_167} :catchall_10a

    goto/16 :goto_25e

    :catchall_169
    move-exception v1

    .line 319
    :try_start_16a
    monitor-exit p0
    :try_end_16b
    .catchall {:try_start_16a .. :try_end_16b} :catchall_169

    :try_start_16b
    throw v1
    :try_end_16c
    .catchall {:try_start_16b .. :try_end_16c} :catchall_10a

    .line 259
    :goto_16c
    :try_start_16c
    monitor-exit p0
    :try_end_16d
    .catchall {:try_start_16c .. :try_end_16d} :catchall_133

    :try_start_16d
    throw v1

    .line 125
    :cond_16e
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->p:Ljava/lang/String;

    invoke-virtual {p0, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result p0

    if-eqz p0, :cond_1aa

    .line 269
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->s:Ljava/lang/Object;

    monitor-enter p0
    :try_end_179
    .catchall {:try_start_16d .. :try_end_179} :catchall_10a

    .line 270
    :try_start_179
    sget-boolean v1, Lcom/wukong/manager/WukongInstrumentationHook;->ab:Z

    monitor-exit p0
    :try_end_17c
    .catchall {:try_start_179 .. :try_end_17c} :catchall_1a7

    if-eqz v1, :cond_25e

    .line 127
    :try_start_17e
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->u:Ljava/util/LinkedHashMap;

    invoke-static {p0}, Lcom/wukong/manager/WukongInstrumentationHook;->e(Ljava/util/LinkedHashMap;)V

    .line 128
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->e:Ljava/lang/String;

    new-instance v1, Ljava/lang/StringBuilder;

    invoke-direct {v1}, Ljava/lang/StringBuilder;-><init>()V

    const/16 v2, 0x1c

    new-array v2, v2, [I

    fill-array-data v2, :array_396

    const v3, 0x1eb37baf

    invoke-static {v2, v3}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v1, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v1

    invoke-static {p0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I
    :try_end_1a5
    .catchall {:try_start_17e .. :try_end_1a5} :catchall_10a

    goto/16 :goto_25e

    :catchall_1a7
    move-exception v1

    .line 271
    :try_start_1a8
    monitor-exit p0
    :try_end_1a9
    .catchall {:try_start_1a8 .. :try_end_1a9} :catchall_1a7

    :try_start_1a9
    throw v1

    .line 132
    :cond_1aa
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->q:Ljava/lang/String;

    invoke-virtual {p0, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result p0

    if-eqz p0, :cond_1e6

    .line 275
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->s:Ljava/lang/Object;

    monitor-enter p0
    :try_end_1b5
    .catchall {:try_start_1a9 .. :try_end_1b5} :catchall_10a

    .line 276
    :try_start_1b5
    sget-boolean v1, Lcom/wukong/manager/WukongInstrumentationHook;->ac:Z

    monitor-exit p0
    :try_end_1b8
    .catchall {:try_start_1b5 .. :try_end_1b8} :catchall_1e3

    if-eqz v1, :cond_25e

    .line 134
    :try_start_1ba
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->v:Ljava/util/LinkedHashMap;

    invoke-static {p0}, Lcom/wukong/manager/WukongInstrumentationHook;->e(Ljava/util/LinkedHashMap;)V

    .line 135
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->e:Ljava/lang/String;

    new-instance v1, Ljava/lang/StringBuilder;

    invoke-direct {v1}, Ljava/lang/StringBuilder;-><init>()V

    const/16 v2, 0x19

    new-array v2, v2, [I

    fill-array-data v2, :array_3d2

    const v3, 0x719c70ae

    invoke-static {v2, v3}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v1, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v1

    invoke-static {p0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I
    :try_end_1e1
    .catchall {:try_start_1ba .. :try_end_1e1} :catchall_10a

    goto/16 :goto_25e

    :catchall_1e3
    move-exception v1

    .line 277
    :try_start_1e4
    monitor-exit p0
    :try_end_1e5
    .catchall {:try_start_1e4 .. :try_end_1e5} :catchall_1e3

    :try_start_1e5
    throw v1

    :cond_1e6
    if-eqz v6, :cond_25e

    .line 311
    sget-object p0, Lcom/wukong/manager/WukongInstrumentationHook;->s:Ljava/lang/Object;

    monitor-enter p0
    :try_end_1eb
    .catchall {:try_start_1e5 .. :try_end_1eb} :catchall_10a

    .line 312
    :try_start_1eb
    sget-boolean v1, Lcom/wukong/manager/WukongInstrumentationHook;->ad:Z

    monitor-exit p0
    :try_end_1ee
    .catchall {:try_start_1eb .. :try_end_1ee} :catchall_237

    if-nez v1, :cond_1f1

    goto :goto_25e

    .line 142
    :cond_1f1
    :try_start_1f1
    invoke-static {v0}, Lcom/wukong/manager/WukongInstrumentationHook;->h(Ljava/lang/String;)Ljava/util/LinkedHashMap;

    move-result-object p0

    .line 143
    invoke-virtual {p0}, Ljava/util/AbstractMap;->isEmpty()Z

    move-result v1

    if-nez v1, :cond_25e

    .line 144
    invoke-static {p0}, Lcom/wukong/manager/WukongInstrumentationHook;->e(Ljava/util/LinkedHashMap;)V

    .line 145
    sget-object v1, Lcom/wukong/manager/WukongInstrumentationHook;->e:Ljava/lang/String;

    new-instance v2, Ljava/lang/StringBuilder;

    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V

    new-array v3, v3, [I

    fill-array-data v3, :array_408

    const v4, 0x4394e25a

    invoke-static {v3, v4}, Lcom/wukong/manager/cz;->h([II)Ljava/lang/String;

    move-result-object v3

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const/4 v3, 0x2

    new-array v3, v3, [J

    fill-array-data v3, :array_43a

    const v4, 0x26213b71

    const/4 v5, 0x6

    invoke-static {v3, v4, v5}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v3

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {p0}, Ljava/util/LinkedHashMap;->keySet()Ljava/util/Set;

    move-result-object p0

    invoke-virtual {v2, p0}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p0

    invoke-static {v1, p0}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I
    :try_end_236
    .catchall {:try_start_1f1 .. :try_end_236} :catchall_10a

    goto :goto_25e

    :catchall_237
    move-exception v1

    .line 313
    :try_start_238
    monitor-exit p0
    :try_end_239
    .catchall {:try_start_238 .. :try_end_239} :catchall_237

    :try_start_239
    throw v1
    :try_end_23a
    .catchall {:try_start_239 .. :try_end_23a} :catchall_10a

    .line 148
    :goto_23a
    sget-object v1, Lcom/wukong/manager/WukongInstrumentationHook;->e:Ljava/lang/String;

    new-instance v2, Ljava/lang/StringBuilder;

    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V

    const/16 v3, 0x8

    new-array v3, v3, [J

    fill-array-data v3, :array_446

    const v4, 0x5bc8b9e7

    const/16 v5, 0x20

    invoke-static {v3, v4, v5}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v3

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    invoke-static {v1, v0, p0}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I

    :cond_25e
    :goto_25e
    return-void

    nop

    :array_260
    .array-data 4
        0x1ff7e051
        0x1fe6b832
        0x1fd53b30
        0x1fc40b68
        0x1fb364ba
        0x1fa25744
        0x1f9131e7
        0x1f80226c
        0x1f6fac9b
        0x1f5ed3ed
        0x1f4df730
        0x1f3c3786
        0x1f2b88e5
        0x1f1ad8c4
        0x1f09b0ad
        0x1ef84821
        0x1ee7646e
        0x1ed6320b
        0x1ec5138e
        0x1eb4103f
        0x1ea3cb03
        0x1e925b95
        0x1e812f9b
        0x1e70bf53
        0x1e5f6533
        0x1e4e8bc6
    .end array-data

    :array_298
    .array-data 4
        -0x27180f3f
        -0x27293e3c
        -0x273a5352
        -0x274b1329
        -0x275cea8f
        -0x276d635c
        -0x277e9a51
        -0x278f71cc
        -0x27a0296d
        -0x27b137dd
        -0x27c25473
        -0x27d305de
        -0x27e447e7
        -0x27f5df52
        -0x28069882
        -0x281704ea
        -0x2828f188
        -0x28397541
    .end array-data

    :array_2c0
    .array-data 4
        0x7fc3f2aa
        0x7fd4cff5
        0x7fe5533f
        0x7ff6a693
        -0x7ff8a0f3
        -0x7fe7446b
        -0x7fd60741
        -0x7fc57a59
        -0x7fb476b5
        -0x7fa384b7
        -0x7f925a6c
        -0x7f81280a
        -0x7f70df64
        -0x7f5f9a26
        -0x7f4ecfe2
        -0x7f3d16b9
        -0x7f2cd887
        -0x7f1bf38c
        -0x7f0adc45
        -0x7ef915ad
        -0x7ee88be1
        -0x7ed7dc44
        -0x7ec68f26
    .end array-data

    :array_2f2
    .array-data 8
        0xb6863d30899L
        0x2b340b87c174L
        0x56526b81f08dL
        0x7a000000302eL
    .end array-data

    :array_306
    .array-data 4
        -0x11a7990d
        -0x11969af4
        -0x118559f2  # -1.9393E28f
        -0x11743294
        -0x116392a0
        -0x11520d5b
        -0x114198f2
        -0x11303d2d
        -0x111f8156
        -0x110ea444
        -0x10fd7d07
        -0x10ec51b1
        -0x10db5396
        -0x10ca8dfb
        -0x10b9bd1a
        -0x10a87635
        -0x10970702
        -0x1086e067  # -7.7099967E28f
        -0x1075d6b3
        -0x10643291
        -0x10533886
        -0x10429f4d
        -0x1031fe0c
        -0x1020f0c9
        -0x100f59d0
        -0xffe0537
        -0xfedad01
        -0xfdc734e
        -0xfcb0927
        -0xfba9eef
        -0xfa9c858
        -0xf980860
        -0xf876965
    .end array-data

    :array_34c
    .array-data 4
        -0x7d53d04a
        -0x7d64b394
        -0x7d754685
        -0x7d86fa54
        -0x7d970657
        -0x7da85f52
        -0x7db98c2a
        -0x7dca9044
        -0x7ddbb541
        -0x7deca970
        -0x7dfd05da
        -0x7e0e0d3e
        -0x7e1f6567
        -0x7e3007b2
        -0x7e41809a
        -0x7e52b58f
        -0x7e63278c
        -0x7e7409f7
        -0x7e856d16
        -0x7e96bce9
        -0x7ea7f954
        -0x7eb89aa2
        -0x7ec96897
        -0x7edad790
        -0x7eeb8d3f
        -0x7efc5e9b
        -0x7f0d26ae
        -0x7f1e35cc
        -0x7f2fe233
        -0x7f40dac2
        -0x7f51764a
        -0x7f62e6d6  # -1.44272E-38f
        -0x7f731ede
        -0x7f848ae7
        -0x7f95eb46
    .end array-data

    :array_396
    .array-data 4
        0x7baf1a12
        0x7bc02fd9
        0x7bd12db9
        0x7be25471
        0x7bf3f0d9
        0x7c04b5d3
        0x7c15b848
        0x7c26aadb
        0x7c3708d8
        0x7c48b63b
        0x7c59939b
        0x7c6a779a
        0x7c7b18ce
        0x7c8c5d84
        0x7c9d02e4
        0x7cae04e1
        0x7cbf87be
        0x7cd0f669
        0x7ce1c842
        0x7cf2b3bc
        0x7d0392a0
        0x7d149241
        0x7d255918
        0x7d36c54b
        0x7d47a702
        0x7d5852d0
        0x7d692622
        0x7d7acb21
    .end array-data

    :array_3d2
    .array-data 4
        0x70ae26a1
        0x70bfe50c
        0x70d042d0
        0x70e10b7f
        0x70f2bffb
        0x7103c751
        0x7114651a
        0x7125ed94
        0x713615e4
        0x7147ae45
        0x7158dda5
        0x71697c46
        0x717a6bcc
        0x718be962
        0x719c4790
        0x71ad53e9
        0x71be06c8
        0x71cfc799
        0x71e087e4
        0x71f115fc
        0x72025a19
        0x72137d50
        0x72244a68
        0x72358861
        0x7246ab97
    .end array-data

    :array_408
    .array-data 4
        -0x1c2f9878
        -0x1c40534a
        -0x1c516092
        -0x1c626f11
        -0x1c7314b7
        -0x1c8438a9
        -0x1c950bb4
        -0x1ca66fd8
        -0x1cb752d9
        -0x1cc8c9c8
        -0x1cd9f232
        -0x1cea621d
        -0x1cfbc528
        -0x1d0c6125
        -0x1d1d66ce  # -2.0900015E21f
        -0x1d2e1d1e
        -0x1d3fe484
        -0x1d502aad
        -0x1d61e8c5
        -0x1d72d753
        -0x1d8391fe
        -0x1d948175
        -0x1da5abbb
    .end array-data

    :array_43a
    .array-data 8
        0x22963b98c7c3L
        0x67210000d21dL
    .end array-data

    :array_446
    .array-data 8
        0x4dc871d0d863L
        0x5ca2394a5095L
        0x2f6f53b2140aL
        0x1c2d057d03e3L
        0x79262fe077f8L
        0x7f08738caa02L
        0x20b7e92f939aL
        0x3aa7e533cffcL
    .end array-data
.end method

.method private static k()Z
    .registers 5

    const v0, 0x1e1daa1c

    const/4 v1, 0x0

    .line 281
    invoke-static {v0, v1}, Lcom/wukong/manager/cy;->h(ILjava/lang/Object;)I

    const/16 v0, 0x1a

    .line 301
    :try_start_9
    new-array v0, v0, [I

    fill-array-data v0, :array_5a

    const v2, 0x6238a046

    invoke-static {v0, v2}, Lcom/wukong/manager/cz;->f([II)Ljava/lang/String;

    move-result-object v0

    invoke-static {v0}, Ljava/lang/Class;->forName(Ljava/lang/String;)Ljava/lang/Class;

    move-result-object v0

    const/4 v2, 0x5

    .line 302
    new-array v2, v2, [J

    fill-array-data v2, :array_92

    const v3, 0x53ed85ee

    const/16 v4, 0x12

    invoke-static {v2, v3, v4}, Lcom/wukong/manager/cz;->g([JII)Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v0, v2, v1}, Ljava/lang/Class;->getDeclaredMethod(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;

    move-result-object v0

    .line 303
    invoke-virtual {v0, v1, v1}, Ljava/lang/reflect/Method;->invoke(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;

    move-result-object v0

    .line 304
    instance-of v2, v0, Landroid/content/Context;

    if-eqz v2, :cond_37

    check-cast v0, Landroid/content/Context;
    :try_end_36
    .catchall {:try_start_9 .. :try_end_36} :catchall_37

    move-object v1, v0

    :catchall_37
    :cond_37
    if-eqz v1, :cond_3d

    .line 285
    :try_start_39
    invoke-static {v1}, Lcom/wukong/manager/WukongInstrumentationHook;->g(Landroid/content/Context;)V

    goto :goto_4b

    .line 287
    :cond_3d
    sget-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->s:Ljava/lang/Object;

    monitor-enter v0
    :try_end_40
    .catchall {:try_start_39 .. :try_end_40} :catchall_57

    .line 288
    :try_start_40
    sget-boolean v1, Lcom/wukong/manager/WukongInstrumentationHook;->w:Z

    if-nez v1, :cond_4a

    .line 289
    invoke-static {}, Lcom/wukong/manager/WukongInstrumentationHook;->i()V

    goto :goto_4a

    :catchall_48
    move-exception v1

    goto :goto_55

    .line 291
    :cond_4a
    :goto_4a
    monitor-exit v0
    :try_end_4b
    .catchall {:try_start_40 .. :try_end_4b} :catchall_48

    .line 275
    :goto_4b
    :try_start_4b
    sget-object v0, Lcom/wukong/manager/WukongInstrumentationHook;->s:Ljava/lang/Object;

    monitor-enter v0
    :try_end_4e
    .catchall {:try_start_4b .. :try_end_4e} :catchall_57

    .line 276
    :try_start_4e
    sget-boolean v1, Lcom/wukong/manager/WukongInstrumentationHook;->ac:Z

    monitor-exit v0

    return v1

    :catchall_52
    move-exception v1

    .line 277
    monitor-exit v0
    :try_end_54
    .catchall {:try_start_4e .. :try_end_54} :catchall_52

    :try_start_54
    throw v1
    :try_end_55
    .catchall {:try_start_54 .. :try_end_55} :catchall_57

    .line 291
    :goto_55
    :try_start_55
    monitor-exit v0
    :try_end_56
    .catchall {:try_start_55 .. :try_end_56} :catchall_48

    :try_start_56
    throw v1
    :try_end_57
    .catchall {:try_start_56 .. :try_end_57} :catchall_57

    :catchall_57
    const/4 v0, 0x0

    return v0

    nop

    :array_5a
    .array-data 4
        -0x5fb92a99
        -0x5fa8971d
        -0x5f97d2df
        -0x5f86cb7a
        -0x5f753283
        -0x5f64ccb8
        -0x5f5353c6
        -0x5f42ad3f
        -0x5f31fb45
        -0x5f20dd55
        -0x5f0ffe19
        -0x5efe0219
        -0x5eed50a2
        -0x5edc5e54
        -0x5ecbb88b
        -0x5eba26fb
        -0x5ea95a20
        -0x5e988a0d
        -0x5e871cb3
        -0x5e7673e9
        -0x5e654332
        -0x5e5475e6
        -0x5e4390a4
        -0x5e32b46a
        -0x5e21ef83
        -0x5e106512
    .end array-data

    :array_92
    .array-data 8
        0x5222d7f040c2L
        0x2ea421e322d7L
        0x4a286a7cabb5L
        0x3a82849d8a2L
        0x37bd00000163L
    .end array-data
.end method

.method public static onApplicationAttached(Landroid/content/Context;)V
    .registers 3

    const/4 v0, 0x0

    const v1, 0x35ee3ce3

    .line 500
    invoke-static {v1, v0}, Lcom/wukong/manager/cy;->h(ILjava/lang/Object;)I

    move-result v0

    .line 501
    invoke-static {v0, v1}, Lcom/wukong/manager/cy;->i(II)Z

    move-result v0

    if-eqz v0, :cond_11

    .line 502
    invoke-static {p0}, Lcom/wukong/manager/WukongInstrumentationHook;->j(Landroid/content/Context;)V

    :cond_11
    return-void
.end method
