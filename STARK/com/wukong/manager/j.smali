.class final Lcom/wukong/manager/j;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x1ff4336f

.field private static f:I = 0x30b3ac0a

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/16 v0, 0x8

    .line 618
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/j;->g:[I

    return-void

    :array_a
    .array-data 4
        0x73e798c9
        0x37e4652d
        0x759d3712
        0x413be7ac
        0x50fcaa59
        0x2a0a1f1e
        0x68912274
        0x165a1848
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

    const v1, 0x653739bf

    xor-int/2addr v1, p0

    .line 652
    sget-object v2, Lcom/wukong/manager/j;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x469b491f

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 653
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 656
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x29862d4d

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 657
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 4

    .line 621
    sget-object p1, Lcom/wukong/manager/j;->g:[I

    const v0, 0x7fffffff

    and-int/2addr v0, p0

    array-length v1, p1

    rem-int/2addr v0, v1

    aget p1, p1, v0

    xor-int/2addr p0, p1

    const/4 p1, 0x0

    :goto_c
    const/4 v0, 0x3

    if-ge p1, v0, :cond_23

    .line 623
    sget v0, Lcom/wukong/manager/j;->e:I

    mul-int/lit16 v1, p1, 0x101

    xor-int/2addr v0, v1

    add-int/2addr p0, v0

    const/4 v0, 0x5

    .line 624
    invoke-static {p0, v0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result v0

    const/4 v1, 0x7

    invoke-static {p0, v1}, Ljava/lang/Integer;->rotateRight(II)I

    move-result p0

    xor-int/2addr p0, v0

    add-int/lit8 p1, p1, 0x1

    goto :goto_c

    .line 626
    :cond_23
    sget p1, Lcom/wukong/manager/j;->e:I

    xor-int/2addr p1, p0

    sput p1, Lcom/wukong/manager/j;->e:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 630
    sget v0, Lcom/wukong/manager/j;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/j;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 631
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 632
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/am;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 633
    sget-object p1, Lcom/wukong/manager/j;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x9

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

    .line 637
    :cond_3
    sget v0, Lcom/wukong/manager/j;->e:I

    sget v1, Lcom/wukong/manager/j;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/cr;->f(ILjava/lang/Object;)I

    move-result v0

    .line 638
    invoke-static {v0, p1}, Lcom/wukong/manager/e;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 639
    sget v1, Lcom/wukong/manager/j;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/j;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x9

    .line 643
    invoke-static {p0, p1}, Lcom/wukong/manager/j;->f(ILjava/lang/Object;)I

    move-result p0

    .line 644
    invoke-static {p0, p1}, Lcom/wukong/manager/am;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 645
    sget v0, Lcom/wukong/manager/j;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/cr;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 646
    :cond_17
    sget p1, Lcom/wukong/manager/j;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/e;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
