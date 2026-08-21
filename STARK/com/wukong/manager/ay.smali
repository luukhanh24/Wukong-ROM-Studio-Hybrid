.class final Lcom/wukong/manager/ay;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x5f19f15a

.field private static f:I = 0xac9e018

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/16 v0, 0x8

    .line 3950
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/ay;->g:[I

    return-void

    :array_a
    .array-data 4
        0x2581caa5
        0x5cef1553
        0x1e5a921d
        0x2fad14db
        0x29696e49
        0x22f5759a
        0x353b5702
        0x17ec2f3
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

    const v1, 0xab71859

    xor-int/2addr v1, p0

    .line 3984
    sget-object v2, Lcom/wukong/manager/ay;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x114745e0

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 3985
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 3988
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x1bb20d5b

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 3989
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 5

    .line 3953
    sget-object p1, Lcom/wukong/manager/ay;->g:[I

    const v0, 0x7fffffff

    and-int/2addr v0, p0

    array-length v1, p1

    rem-int/2addr v0, v1

    aget p1, p1, v0

    xor-int/2addr p0, p1

    const/4 p1, 0x0

    :goto_c
    const/4 v0, 0x7

    if-ge p1, v0, :cond_22

    .line 3955
    sget v1, Lcom/wukong/manager/ay;->e:I

    mul-int/lit16 v2, p1, 0x101

    xor-int/2addr v1, v2

    add-int/2addr p0, v1

    const/4 v1, 0x5

    .line 3956
    invoke-static {p0, v1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result v1

    invoke-static {p0, v0}, Ljava/lang/Integer;->rotateRight(II)I

    move-result p0

    xor-int/2addr p0, v1

    add-int/lit8 p1, p1, 0x1

    goto :goto_c

    .line 3958
    :cond_22
    sget p1, Lcom/wukong/manager/ay;->e:I

    xor-int/2addr p1, p0

    sput p1, Lcom/wukong/manager/ay;->e:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 3962
    sget v0, Lcom/wukong/manager/ay;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/ay;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 3963
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 3964
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/al;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 3965
    sget-object p1, Lcom/wukong/manager/ay;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x4f

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

    .line 3969
    :cond_3
    sget v0, Lcom/wukong/manager/ay;->e:I

    sget v1, Lcom/wukong/manager/ay;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/ck;->f(ILjava/lang/Object;)I

    move-result v0

    .line 3970
    invoke-static {v0, p1}, Lcom/wukong/manager/at;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 3971
    sget v1, Lcom/wukong/manager/ay;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/ay;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x4f

    .line 3975
    invoke-static {p0, p1}, Lcom/wukong/manager/ay;->f(ILjava/lang/Object;)I

    move-result p0

    .line 3976
    invoke-static {p0, p1}, Lcom/wukong/manager/al;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 3977
    sget v0, Lcom/wukong/manager/ay;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/ck;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 3978
    :cond_17
    sget p1, Lcom/wukong/manager/ay;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/at;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
