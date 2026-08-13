.class final Lcom/wukong/manager/aq;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0xfd6d46

.field private static f:I = 0x8f6ac0f

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/16 v0, 0x8

    .line 2760
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/aq;->g:[I

    return-void

    :array_a
    .array-data 4
        0x74568dac
        0x290e63f7
        0x14fc6d0d
        0x16ab18ea
        0xa2da10a
        0x5ba4e602
        0x61e73213
        0x237703c3
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

    const v1, 0x43a4e935

    xor-int/2addr v1, p0

    .line 2794
    sget-object v2, Lcom/wukong/manager/aq;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x49fd673

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 2795
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 2798
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x7ba5bc02

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 2799
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 4

    .line 2763
    sget-object p1, Lcom/wukong/manager/aq;->g:[I

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

    .line 2765
    sget v0, Lcom/wukong/manager/aq;->e:I

    mul-int/lit16 v1, p1, 0x101

    xor-int/2addr v0, v1

    add-int/2addr p0, v0

    const/4 v0, 0x5

    .line 2766
    invoke-static {p0, v0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result v0

    const/4 v1, 0x7

    invoke-static {p0, v1}, Ljava/lang/Integer;->rotateRight(II)I

    move-result p0

    xor-int/2addr p0, v0

    add-int/lit8 p1, p1, 0x1

    goto :goto_c

    .line 2768
    :cond_23
    sget p1, Lcom/wukong/manager/aq;->e:I

    xor-int/2addr p1, p0

    sput p1, Lcom/wukong/manager/aq;->e:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 2772
    sget v0, Lcom/wukong/manager/aq;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/aq;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 2773
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 2774
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/r;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 2775
    sget-object p1, Lcom/wukong/manager/aq;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x36

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

    .line 2779
    :cond_3
    sget v0, Lcom/wukong/manager/aq;->e:I

    sget v1, Lcom/wukong/manager/aq;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/cb;->f(ILjava/lang/Object;)I

    move-result v0

    .line 2780
    invoke-static {v0, p1}, Lcom/wukong/manager/cr;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 2781
    sget v1, Lcom/wukong/manager/aq;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/aq;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x36

    .line 2785
    invoke-static {p0, p1}, Lcom/wukong/manager/aq;->f(ILjava/lang/Object;)I

    move-result p0

    .line 2786
    invoke-static {p0, p1}, Lcom/wukong/manager/r;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 2787
    sget v0, Lcom/wukong/manager/aq;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/cb;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 2788
    :cond_17
    sget p1, Lcom/wukong/manager/aq;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/cr;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
