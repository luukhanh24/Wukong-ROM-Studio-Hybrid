.class final Lcom/wukong/manager/bi;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x6bab2fd8

.field private static f:I = 0x19c92143

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/16 v0, 0x8

    .line 4426
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/bi;->g:[I

    return-void

    :array_a
    .array-data 4
        0x4c4dea03  # 5.3979148E7f
        0x368a580f
        0x613f7a97
        0x4c961a0e  # 7.869656E7f
        0x39b07af0
        0xbb0e73f
        0x51a10cfe
        0x2317072
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

    const v1, 0x5499809

    xor-int/2addr v1, p0

    .line 4460
    sget-object v2, Lcom/wukong/manager/bi;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x3d1b3f15

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 4461
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 4464
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x37d99607

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 4465
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 5

    .line 4429
    sget-object p1, Lcom/wukong/manager/bi;->g:[I

    const v0, 0x7fffffff

    and-int/2addr v0, p0

    array-length v1, p1

    rem-int/2addr v0, v1

    aget p1, p1, v0

    xor-int/2addr p0, p1

    const/4 p1, 0x0

    :goto_c
    const/4 v0, 0x5

    if-ge p1, v0, :cond_22

    .line 4431
    sget v1, Lcom/wukong/manager/bi;->e:I

    mul-int/lit16 v2, p1, 0x101

    xor-int/2addr v1, v2

    add-int/2addr p0, v1

    .line 4432
    invoke-static {p0, v0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result v0

    const/4 v1, 0x7

    invoke-static {p0, v1}, Ljava/lang/Integer;->rotateRight(II)I

    move-result p0

    xor-int/2addr p0, v0

    add-int/lit8 p1, p1, 0x1

    goto :goto_c

    .line 4434
    :cond_22
    sget p1, Lcom/wukong/manager/bi;->e:I

    xor-int/2addr p1, p0

    sput p1, Lcom/wukong/manager/bi;->e:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 4438
    sget v0, Lcom/wukong/manager/bi;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/bi;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 4439
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 4440
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/be;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 4441
    sget-object p1, Lcom/wukong/manager/bi;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x59

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

    .line 4445
    :cond_3
    sget v0, Lcom/wukong/manager/bi;->e:I

    sget v1, Lcom/wukong/manager/bi;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/ad;->f(ILjava/lang/Object;)I

    move-result v0

    .line 4446
    invoke-static {v0, p1}, Lcom/wukong/manager/cq;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 4447
    sget v1, Lcom/wukong/manager/bi;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/bi;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x59

    .line 4451
    invoke-static {p0, p1}, Lcom/wukong/manager/bi;->f(ILjava/lang/Object;)I

    move-result p0

    .line 4452
    invoke-static {p0, p1}, Lcom/wukong/manager/be;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 4453
    sget v0, Lcom/wukong/manager/bi;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/ad;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 4454
    :cond_17
    sget p1, Lcom/wukong/manager/bi;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/cq;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
