.class final Lcom/wukong/manager/cz;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static final e:I = 0xaa


# direct methods
.method private constructor <init>()V
    .registers 1

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method

.method private static e(II)I
    .registers 5

    .line 180
    invoke-static {p0, p1}, Lcom/wukong/manager/cy;->g(II)I

    move-result v0

    and-int/lit8 v1, p0, 0x3

    mul-int/lit8 v1, v1, 0x8

    add-int/lit16 v2, p1, 0xaa

    mul-int/lit8 p0, p0, 0x1f

    add-int/2addr p0, v2

    ushr-int/2addr p1, v1

    and-int/lit16 p1, p1, 0xff

    add-int/2addr p0, p1

    xor-int/2addr p0, v0

    and-int/lit16 p0, p0, 0xff

    return p0
.end method

.method public static f([II)Ljava/lang/String;
    .registers 6

    .line 155
    array-length v0, p0

    new-array v0, v0, [B

    const/4 v1, 0x0

    .line 156
    :goto_4
    array-length v2, p0

    if-ge v1, v2, :cond_16

    .line 157
    invoke-static {v1, p1}, Lcom/wukong/manager/cz;->e(II)I

    move-result v2

    .line 158
    aget v3, p0, v1

    xor-int/2addr v2, v3

    and-int/lit16 v2, v2, 0xff

    int-to-byte v2, v2

    aput-byte v2, v0, v1

    add-int/lit8 v1, v1, 0x1

    goto :goto_4

    .line 160
    :cond_16
    new-instance p0, Ljava/lang/String;

    sget-object p1, Ljava/nio/charset/StandardCharsets;->UTF_8:Ljava/nio/charset/Charset;

    invoke-direct {p0, v0, p1}, Ljava/lang/String;-><init>([BLjava/nio/charset/Charset;)V

    return-object p0
.end method

.method public static g([JII)Ljava/lang/String;
    .registers 9

    .line 163
    new-array v0, p2, [B

    const/4 v1, 0x0

    :goto_3
    if-ge v1, p2, :cond_1f

    ushr-int/lit8 v2, v1, 0x2

    .line 165
    aget-wide v2, p0, v2

    and-int/lit8 v4, v1, 0x3

    mul-int/lit8 v4, v4, 0x8

    ushr-long/2addr v2, v4

    const-wide/16 v4, 0xff

    and-long/2addr v2, v4

    long-to-int v2, v2

    .line 167
    invoke-static {v1, p1}, Lcom/wukong/manager/cz;->e(II)I

    move-result v3

    xor-int/2addr v2, v3

    and-int/lit16 v2, v2, 0xff

    int-to-byte v2, v2

    aput-byte v2, v0, v1

    add-int/lit8 v1, v1, 0x1

    goto :goto_3

    .line 169
    :cond_1f
    new-instance p0, Ljava/lang/String;

    sget-object p1, Ljava/nio/charset/StandardCharsets;->UTF_8:Ljava/nio/charset/Charset;

    invoke-direct {p0, v0, p1}, Ljava/lang/String;-><init>([BLjava/nio/charset/Charset;)V

    return-object p0
.end method

.method public static h([II)Ljava/lang/String;
    .registers 7

    .line 172
    array-length v0, p0

    new-array v0, v0, [B

    const/4 v1, 0x0

    .line 173
    :goto_4
    array-length v2, p0

    if-ge v1, v2, :cond_1a

    .line 174
    array-length v2, p0

    add-int/lit8 v2, v2, -0x1

    sub-int/2addr v2, v1

    .line 175
    aget v3, p0, v1

    invoke-static {v2, p1}, Lcom/wukong/manager/cz;->e(II)I

    move-result v4

    xor-int/2addr v3, v4

    and-int/lit16 v3, v3, 0xff

    int-to-byte v3, v3

    aput-byte v3, v0, v2

    add-int/lit8 v1, v1, 0x1

    goto :goto_4

    .line 177
    :cond_1a
    new-instance p0, Ljava/lang/String;

    sget-object p1, Ljava/nio/charset/StandardCharsets;->UTF_8:Ljava/nio/charset/Charset;

    invoke-direct {p0, v0, p1}, Ljava/lang/String;-><init>([BLjava/nio/charset/Charset;)V

    return-object p0
.end method
