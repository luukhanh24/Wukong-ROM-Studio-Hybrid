.class final Lcom/wukong/manager/ck;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x3374291b

.field private static f:I = 0x5a1d9239

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/4 v0, 0x7

    .line 811
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/ck;->g:[I

    return-void

    nop

    :array_a
    .array-data 4
        0x512c1def
        0x363418e2
        0x17f9b5a8
        0x702166f2
        0x7323624b
        0x5c4d1aa0
        0x156f01bd
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

    const v1, 0x3df2d943

    xor-int/2addr v1, p0

    .line 843
    sget-object v2, Lcom/wukong/manager/ck;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x7d65f9af

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 844
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 847
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x76eb60cf

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 848
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 3

    .line 815
    :try_start_0
    sget v0, Lcom/wukong/manager/ck;->e:I

    or-int/lit8 v0, v0, 0x1

    and-int/lit16 v0, v0, 0xff

    div-int v0, p0, v0

    sget p0, Lcom/wukong/manager/ck;->f:I
    :try_end_a
    .catch Ljava/lang/ArithmeticException; {:try_start_0 .. :try_end_a} :catch_c

    xor-int/2addr p0, v0

    goto :goto_f

    :catch_c
    sget v0, Lcom/wukong/manager/ck;->e:I

    xor-int/2addr p0, v0

    :goto_f
    if-eqz p1, :cond_1e

    .line 816
    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/Class;->getName()Ljava/lang/String;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/String;->length()I

    move-result p1

    add-int/2addr p0, p1

    .line 817
    :cond_1e
    sget p1, Lcom/wukong/manager/ck;->f:I

    xor-int/2addr p1, p0

    sput p1, Lcom/wukong/manager/ck;->f:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 821
    sget v0, Lcom/wukong/manager/ck;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/ck;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 822
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 823
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/ai;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 824
    sget-object p1, Lcom/wukong/manager/ck;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0xd

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

    .line 828
    :cond_3
    sget v0, Lcom/wukong/manager/ck;->e:I

    sget v1, Lcom/wukong/manager/ck;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/bd;->f(ILjava/lang/Object;)I

    move-result v0

    .line 829
    invoke-static {v0, p1}, Lcom/wukong/manager/d;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 830
    sget v1, Lcom/wukong/manager/ck;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/ck;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0xd

    .line 834
    invoke-static {p0, p1}, Lcom/wukong/manager/ck;->f(ILjava/lang/Object;)I

    move-result p0

    .line 835
    invoke-static {p0, p1}, Lcom/wukong/manager/ai;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 836
    sget v0, Lcom/wukong/manager/ck;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/bd;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 837
    :cond_17
    sget p1, Lcom/wukong/manager/ck;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/d;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
