.class final Lcom/wukong/manager/d;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x120dfd10

.field private static f:I = 0x1e386cf4

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/4 v0, 0x6

    .line 1715
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/d;->g:[I

    return-void

    nop

    :array_a
    .array-data 4
        0x6bc940cb
        0x4b526fb5  # 1.3791157E7f
        0x3187b568
        0x42623bd3
        0x220f78ba
        0x14eed89e
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

    const v1, 0x991b4df

    xor-int/2addr v1, p0

    .line 1750
    sget-object v2, Lcom/wukong/manager/d;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x35da4847

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 1751
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 1754
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x1fcc44e

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 1755
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 4

    .line 1718
    sget p1, Lcom/wukong/manager/d;->e:I

    sget v0, Lcom/wukong/manager/d;->f:I

    add-int/2addr p1, v0

    xor-int/2addr p0, p1

    const/4 p1, 0x0

    :goto_7
    const/4 v0, 0x5

    if-ge p1, v0, :cond_1e

    .line 1721
    sget-object v0, Lcom/wukong/manager/d;->g:[I

    array-length v1, v0

    rem-int v1, p1, v1

    aget v0, v0, v1

    add-int/2addr v0, p0

    and-int/lit8 v1, p1, 0xf

    add-int/lit8 v1, v1, 0x1

    invoke-static {v0, v1}, Ljava/lang/Integer;->rotateRight(II)I

    move-result v0

    xor-int/2addr p0, v0

    add-int/lit8 p1, p1, 0x1

    goto :goto_7

    :cond_1e
    mul-int/lit8 p1, p0, 0x21

    ushr-int/lit8 p0, p0, 0x9

    xor-int/2addr p0, p1

    .line 1724
    sput p0, Lcom/wukong/manager/d;->e:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 1728
    sget v0, Lcom/wukong/manager/d;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/d;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 1729
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 1730
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/ce;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 1731
    sget-object p1, Lcom/wukong/manager/d;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x20

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

    .line 1735
    :cond_3
    sget v0, Lcom/wukong/manager/d;->e:I

    sget v1, Lcom/wukong/manager/d;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/ca;->f(ILjava/lang/Object;)I

    move-result v0

    .line 1736
    invoke-static {v0, p1}, Lcom/wukong/manager/bo;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 1737
    sget v1, Lcom/wukong/manager/d;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/d;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x20

    .line 1741
    invoke-static {p0, p1}, Lcom/wukong/manager/d;->f(ILjava/lang/Object;)I

    move-result p0

    .line 1742
    invoke-static {p0, p1}, Lcom/wukong/manager/ce;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 1743
    sget v0, Lcom/wukong/manager/d;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/ca;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 1744
    :cond_17
    sget p1, Lcom/wukong/manager/d;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/bo;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
