.class final Lcom/wukong/manager/bf;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x6b52d40c

.field private static f:I = 0x25ef9744

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/4 v0, 0x6

    .line 2667
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/bf;->g:[I

    return-void

    nop

    :array_a
    .array-data 4
        0x711c3b5b
        0x7e9ce09c
        0x75aa71ed
        0x29c0cef9
        0x4b2b0055  # 1.1206741E7f
        0x6e28bf70
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

    const v1, 0x3770ceae

    xor-int/2addr v1, p0

    .line 2702
    sget-object v2, Lcom/wukong/manager/bf;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x1433b4d

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 2703
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 2706
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x1d9a0608

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 2707
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 4

    .line 2670
    sget p1, Lcom/wukong/manager/bf;->e:I

    sget v0, Lcom/wukong/manager/bf;->f:I

    add-int/2addr p1, v0

    xor-int/2addr p0, p1

    const/4 p1, 0x0

    :goto_7
    const/4 v0, 0x5

    if-ge p1, v0, :cond_1e

    .line 2673
    sget-object v0, Lcom/wukong/manager/bf;->g:[I

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

    .line 2676
    sput p0, Lcom/wukong/manager/bf;->e:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 2680
    sget v0, Lcom/wukong/manager/bf;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/bf;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 2681
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 2682
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/af;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 2683
    sget-object p1, Lcom/wukong/manager/bf;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x34

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

    .line 2687
    :cond_3
    sget v0, Lcom/wukong/manager/bf;->e:I

    sget v1, Lcom/wukong/manager/bf;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/z;->f(ILjava/lang/Object;)I

    move-result v0

    .line 2688
    invoke-static {v0, p1}, Lcom/wukong/manager/bs;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 2689
    sget v1, Lcom/wukong/manager/bf;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/bf;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x34

    .line 2693
    invoke-static {p0, p1}, Lcom/wukong/manager/bf;->f(ILjava/lang/Object;)I

    move-result p0

    .line 2694
    invoke-static {p0, p1}, Lcom/wukong/manager/af;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 2695
    sget v0, Lcom/wukong/manager/bf;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/z;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 2696
    :cond_17
    sget p1, Lcom/wukong/manager/bf;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/bs;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
