.class final Lcom/wukong/manager/cm;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x2e605811

.field private static f:I = 0x19741062

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 5

    const v0, 0x65547300

    const v1, 0x7c53015f

    const v2, 0x50bcdbed

    const v3, 0x74441fef

    const v4, 0x30b338b

    .line 1427
    filled-new-array {v2, v3, v4, v0, v1}, [I

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/cm;->g:[I

    return-void
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

    const v1, 0x4b83bab6  # 1.7266028E7f

    xor-int/2addr v1, p0

    .line 1464
    sget-object v2, Lcom/wukong/manager/cm;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x400136d0

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 1465
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 1468
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x4dfb63e9  # 5.2720362E8f

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 1469
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 4

    .line 1430
    sget p1, Lcom/wukong/manager/cm;->f:I

    add-int/2addr p0, p1

    .line 1431
    sget p1, Lcom/wukong/manager/cm;->e:I

    xor-int v0, p0, p1

    and-int/lit8 v0, v0, 0x7

    if-eqz v0, :cond_29

    const/4 v1, 0x1

    if-eq v0, v1, :cond_21

    const/4 v1, 0x2

    if-eq v0, v1, :cond_1c

    const/4 v1, 0x3

    if-eq v0, v1, :cond_17

    ushr-int/2addr p1, v1

    :goto_15
    xor-int/2addr p0, p1

    goto :goto_2f

    :cond_17
    shl-int/lit8 p1, p0, 0x3

    sub-int p0, p1, p0

    goto :goto_2f

    .line 1434
    :cond_1c
    invoke-static {p0}, Ljava/lang/Integer;->reverse(I)I

    move-result p0

    goto :goto_2f

    .line 1433
    :cond_21
    sget-object p1, Lcom/wukong/manager/cm;->g:[I

    array-length v0, p1

    sub-int/2addr v0, v1

    aget p1, p1, v0

    add-int/2addr p0, p1

    goto :goto_2f

    .line 1432
    :cond_29
    sget-object p1, Lcom/wukong/manager/cm;->g:[I

    const/4 v0, 0x0

    aget p1, p1, v0

    goto :goto_15

    :goto_2f
    const p1, 0x6d2b79f5

    add-int/2addr p1, p0

    .line 1438
    sput p1, Lcom/wukong/manager/cm;->f:I

    .line 1439
    sget p1, Lcom/wukong/manager/cm;->e:I

    xor-int/2addr p0, p1

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 1442
    sget v0, Lcom/wukong/manager/cm;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/cm;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 1443
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 1444
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/ay;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 1445
    sget-object p1, Lcom/wukong/manager/cm;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x1a

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

    .line 1449
    :cond_3
    sget v0, Lcom/wukong/manager/cm;->e:I

    sget v1, Lcom/wukong/manager/cm;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/ce;->f(ILjava/lang/Object;)I

    move-result v0

    .line 1450
    invoke-static {v0, p1}, Lcom/wukong/manager/k;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 1451
    sget v1, Lcom/wukong/manager/cm;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/cm;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x1a

    .line 1455
    invoke-static {p0, p1}, Lcom/wukong/manager/cm;->f(ILjava/lang/Object;)I

    move-result p0

    .line 1456
    invoke-static {p0, p1}, Lcom/wukong/manager/ay;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 1457
    sget v0, Lcom/wukong/manager/cm;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/ce;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 1458
    :cond_17
    sget p1, Lcom/wukong/manager/cm;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/k;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
