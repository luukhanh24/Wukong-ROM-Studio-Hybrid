.class final Lcom/wukong/manager/k;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x707f9592

.field private static f:I = 0x12adaba1

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/16 v0, 0x8

    .line 4188
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/k;->g:[I

    return-void

    :array_a
    .array-data 4
        0x53c17995
        0x3d8527ee
        0x5ee87cd7
        0x3b4b43c0
        0x5238cb82
        0x6bf9e82b
        0x39fd6f29
        0x5479fa6a
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

    const v1, 0x458f1a66

    xor-int/2addr v1, p0

    .line 4222
    sget-object v2, Lcom/wukong/manager/k;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x2b877f60

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 4223
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 4226
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x645d32b4

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 4227
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 5

    .line 4191
    sget-object p1, Lcom/wukong/manager/k;->g:[I

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

    .line 4193
    sget v1, Lcom/wukong/manager/k;->e:I

    mul-int/lit16 v2, p1, 0x101

    xor-int/2addr v1, v2

    add-int/2addr p0, v1

    const/4 v1, 0x5

    .line 4194
    invoke-static {p0, v1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result v1

    invoke-static {p0, v0}, Ljava/lang/Integer;->rotateRight(II)I

    move-result p0

    xor-int/2addr p0, v1

    add-int/lit8 p1, p1, 0x1

    goto :goto_c

    .line 4196
    :cond_22
    sget p1, Lcom/wukong/manager/k;->e:I

    xor-int/2addr p1, p0

    sput p1, Lcom/wukong/manager/k;->e:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 4200
    sget v0, Lcom/wukong/manager/k;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/k;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 4201
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 4202
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/h;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 4203
    sget-object p1, Lcom/wukong/manager/k;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x54

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

    .line 4207
    :cond_3
    sget v0, Lcom/wukong/manager/k;->e:I

    sget v1, Lcom/wukong/manager/k;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/aw;->f(ILjava/lang/Object;)I

    move-result v0

    .line 4208
    invoke-static {v0, p1}, Lcom/wukong/manager/av;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 4209
    sget v1, Lcom/wukong/manager/k;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/k;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x54

    .line 4213
    invoke-static {p0, p1}, Lcom/wukong/manager/k;->f(ILjava/lang/Object;)I

    move-result p0

    .line 4214
    invoke-static {p0, p1}, Lcom/wukong/manager/h;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 4215
    sget v0, Lcom/wukong/manager/k;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/aw;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 4216
    :cond_17
    sget p1, Lcom/wukong/manager/k;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/av;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
