.class final Lcom/wukong/manager/q;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x30383439

.field private static f:I = 0x15d82069

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/4 v0, 0x7

    .line 2477
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/q;->g:[I

    return-void

    nop

    :array_a
    .array-data 4
        0x45724708
        0x34c2a175
        0x38491b5d
        0x45b953a
        0x599ea758
        0x44e11202
        0x5e9fb3c8
    .end array-data
.end method

.method private constructor <init>()V
    .registers 1

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method

.method public static e(II)I
    .registers 6

    xor-int/2addr p0, p1

    const p1, 0x7fffffff

    and-int v0, p0, p1

    const v1, 0x25e47106

    xor-int/2addr v1, p0

    .line 2509
    sget-object v2, Lcom/wukong/manager/q;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0xaaa0dce

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 2510
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 2513
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x374927fa

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 2514
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 3

    .line 2481
    :try_start_0
    sget v0, Lcom/wukong/manager/q;->e:I

    or-int/lit8 v0, v0, 0x1

    and-int/lit16 v0, v0, 0xff

    div-int v0, p0, v0

    sget p0, Lcom/wukong/manager/q;->f:I
    :try_end_a
    .catch Ljava/lang/ArithmeticException; {:try_start_0 .. :try_end_a} :catch_c

    xor-int/2addr p0, v0

    goto :goto_f

    :catch_c
    sget v0, Lcom/wukong/manager/q;->e:I

    xor-int/2addr p0, v0

    :goto_f
    if-eqz p1, :cond_1e

    .line 2482
    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/Class;->getName()Ljava/lang/String;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/String;->length()I

    move-result p1

    add-int/2addr p0, p1

    .line 2483
    :cond_1e
    sget p1, Lcom/wukong/manager/q;->f:I

    xor-int/2addr p1, p0

    sput p1, Lcom/wukong/manager/q;->f:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 2487
    sget v0, Lcom/wukong/manager/q;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/q;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 2488
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 2489
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/c;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 2490
    sget-object p1, Lcom/wukong/manager/q;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x30

    and-int/lit8 p1, p1, 0x3

    if-ne p0, p1, :cond_1f

    const/4 p0, 0x1

    return p0

    :cond_1f
    const/4 p0, 0x0

    return p0
.end method

.method public static h(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;
    .registers 4

    if-ne p0, p1, :cond_3

    goto :goto_1a

    .line 2494
    :cond_3
    sget v0, Lcom/wukong/manager/q;->e:I

    sget v1, Lcom/wukong/manager/q;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/r;->f(ILjava/lang/Object;)I

    move-result v0

    .line 2495
    invoke-static {v0, p1}, Lcom/wukong/manager/bu;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 2496
    sget v1, Lcom/wukong/manager/q;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/q;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x30

    .line 2500
    invoke-static {p0, p1}, Lcom/wukong/manager/q;->f(ILjava/lang/Object;)I

    move-result p0

    .line 2501
    invoke-static {p0, p1}, Lcom/wukong/manager/c;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 2502
    sget v0, Lcom/wukong/manager/q;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/r;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 2503
    :cond_17
    sget p1, Lcom/wukong/manager/q;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/bu;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
