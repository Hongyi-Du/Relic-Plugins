// CI-only raw SKP inspection against Skia 95ee33d7ec7791ab9c071675710a14fe6408ae4f.
// No shaping, raster surface, fallback font manager, or canonical element output.
#include "include/core/SkCanvas.h"
#include "include/core/SkData.h"
#include "include/core/SkFont.h"
#include "include/core/SkFontArguments.h"
#include "include/core/SkFontParameters.h"
#include "include/core/SkGraphics.h"
#include "include/core/SkImage.h"
#include "include/core/SkM44.h"
#include "include/core/SkPaint.h"
#include "include/core/SkPicture.h"
#include "include/core/SkSerialProcs.h"
#include "include/core/SkStream.h"
#include "include/core/SkString.h"
#include "include/core/SkTextBlob.h"
#include "include/core/SkTypeface.h"
#include "include/utils/SkNoDrawCanvas.h"
#include "src/core/SkTextBlobPriv.h"

#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <map>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace {
// Small output-only JSON writer. UTF-8 source strings are retained as bytes in hex where
// the upstream API does not promise a Unicode string (blob text, annotations, streams).
struct J {
    enum Kind { Null, Boolean, Number, String, Array, Object } kind = Null;
    bool boolean = false;
    double number = 0;
    std::string string;
    std::vector<J> array;
    std::map<std::string, J> object;
};
J B(bool v) { J j; j.kind=J::Boolean; j.boolean=v; return j; }
J N(double v) { J j; j.kind=J::Number; j.number=v; return j; }
J S(const std::string& v) { J j; j.kind=J::String; j.string=v; return j; }
J A(std::vector<J> v = {}) { J j; j.kind=J::Array; j.array=std::move(v); return j; }
J O(std::initializer_list<std::pair<const std::string, J>> v = {}) {
    J j; j.kind=J::Object; j.object=v; return j;
}
void quoted(std::ostream& out, const std::string& value) {
    out << '"';
    for (unsigned char c : value) {
        switch(c) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\b': out << "\\b"; break;
            case '\f': out << "\\f"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (c < 32) out << "\\u00" << std::hex << std::setw(2) << std::setfill('0')
                                << static_cast<unsigned>(c) << std::dec;
                else out << c;
        }
    }
    out << '"';
}
void json(std::ostream& out, const J& j) {
    switch(j.kind) {
        case J::Null: out << "null"; break;
        case J::Boolean: out << (j.boolean ? "true" : "false"); break;
        case J::Number: out << std::setprecision(17) << j.number; break;
        case J::String: quoted(out,j.string); break;
        case J::Array:
            out << '[';
            for (size_t i=0;i<j.array.size();++i) { if(i)out << ','; json(out,j.array[i]); }
            out << ']'; break;
        case J::Object:
            out << '{';
            { bool first=true; for(const auto& p:j.object) {
                if(!first)out << ','; first=false; quoted(out,p.first); out << ':'; json(out,p.second);
            }} out << '}'; break;
    }
}
std::string hex(const void* data, size_t count) {
    if(!data && count) return {};
    std::ostringstream out;
    const auto* bytes=static_cast<const unsigned char*>(data);
    for(size_t i=0;i<count;++i) out << std::hex << std::setw(2) << std::setfill('0')
                                  << static_cast<unsigned>(bytes[i]);
    return out.str();
}
std::string pointer(const void* p) { std::ostringstream out; out << p; return out.str(); }

struct Context {
    std::string output;
    sk_sp<SkData> input;
    std::vector<J> errors, typefaces, deserializeCalls, images, blobs, annotations, nestedPictures;
    std::vector<sk_sp<SkTypeface>> heldFaces;
    std::vector<const SkTypeface*> callbackFaces;
    uint64_t sequence=0;

    void error(const std::string& message) { errors.push_back(S(message)); }
    J scalar(double value, const char* label) {
        if(!std::isfinite(value)) { error(std::string("Nonfinite actual scalar: ")+label); return {}; }
        return N(value);
    }
    J point(SkPoint p) { return A({scalar(p.x(),"point.x"),scalar(p.y(),"point.y")}); }
    J rect(const SkRect& r) {
        return A({scalar(r.left(),"rect.left"),scalar(r.top(),"rect.top"),
                  scalar(r.right(),"rect.right"),scalar(r.bottom(),"rect.bottom")});
    }
    bool save(const std::string& name, const void* data, size_t size) {
        std::ofstream file(output+"/"+name,std::ios::binary);
        if(!file) { error("Cannot create raw sidecar: "+name); return false; }
        file.write(static_cast<const char*>(data),static_cast<std::streamsize>(size));
        if(!file) { error("Cannot completely write raw sidecar: "+name); return false; }
        return true;
    }
    int face(const sk_sp<SkTypeface>& tf) {
        if(!tf) { error("Actual blob run has null typeface; no fallback requested"); return -1; }
        for(size_t i=0;i<heldFaces.size();++i) if(heldFaces[i].get()==tf.get()) return static_cast<int>(i);
        const int id=static_cast<int>(heldFaces.size());
        heldFaces.push_back(tf);
        const auto style=tf->fontStyle();
        SkString family, postscript;
        tf->getFamilyName(&family);
        const bool psOK=tf->getPostScriptName(&postscript);
        J record=O({{"id",N(id)},{"object_pointer",S(pointer(tf.get()))},{"runtime_unique_id",N(tf->uniqueID())},
                    {"family",S(family.c_str())},{"postscript_query_succeeded",B(psOK)},
                    {"postscript_name",psOK?S(postscript.c_str()):J{}},
                    {"intrinsic_font_style",O({{"weight",N(style.weight())},{"width",N(style.width())},
                                               {"slant",N(static_cast<int>(style.slant()))}})},
                    {"synthetic_bold",B(tf->isSyntheticBold())},{"synthetic_oblique",B(tf->isSyntheticOblique())},
                    {"glyph_count",N(tf->countGlyphs())},
                    {"quantity",S("Actual typeface decoded from this serialized SKP; not a live browser object")}});
        if(!psOK) error("Typeface "+std::to_string(id)+": PostScript name query failed");
        if(tf->countGlyphs()<=0) error("Typeface "+std::to_string(id)+": empty decoded typeface");

        const int positionCount=tf->getVariationDesignPosition({});
        record.object["variation_position_count_query"]=N(positionCount);
        record.object["variation_position_read_count"]=J{};
        record.object["variation_positions"]=J{};
        if(positionCount<0) error("Typeface "+std::to_string(id)+": variation position count query failed");
        else {
            std::vector<SkFontArguments::VariationPosition::Coordinate> coordinates(static_cast<size_t>(positionCount));
            const int actual=tf->getVariationDesignPosition({coordinates.data(),coordinates.size()});
            record.object["variation_position_read_count"]=N(actual);
            if(actual!=positionCount) error("Typeface "+std::to_string(id)+": variation position read count changed/failed");
            else {
                std::vector<J> positions;
                for(const auto& v:coordinates) positions.push_back(O({{"axis_tag_uint32",N(v.axis)},
                                                                    {"value",scalar(v.value,"variation.value")}}));
                record.object["variation_positions"]=A(std::move(positions));
            }
        }
        const int axisCount=tf->getVariationDesignParameters({});
        record.object["variation_parameter_count_query"]=N(axisCount);
        record.object["variation_parameter_read_count"]=J{};
        record.object["variation_parameters"]=J{};
        if(axisCount<0) error("Typeface "+std::to_string(id)+": variation parameter count query failed");
        else {
            std::vector<SkFontParameters::Variation::Axis> axes(static_cast<size_t>(axisCount));
            const int actual=tf->getVariationDesignParameters({axes.data(),axes.size()});
            record.object["variation_parameter_read_count"]=N(actual);
            if(actual!=axisCount) error("Typeface "+std::to_string(id)+": variation parameter read count changed/failed");
            else {
                std::vector<J> values;
                for(const auto& v:axes) values.push_back(O({{"axis_tag_uint32",N(v.tag)},
                    {"min",scalar(v.min,"axis.min")},{"default",scalar(v.def,"axis.default")},
                    {"max",scalar(v.max,"axis.max")},{"hidden",B(v.isHidden())}}));
                record.object["variation_parameters"]=A(std::move(values));
            }
        }
        int collectionIndex=-1;
        auto stream=tf->openStream(&collectionIndex);
        record.object["font_stream"]=J{};
        if(!stream) error("Typeface "+std::to_string(id)+": openStream returned null");
        else {
            const auto before=stream->getPosition();
            const auto size=stream->getLength();
            const bool rewound=stream->rewind();
            J streamRecord=O({{"collection_index",N(collectionIndex)},{"length",N(static_cast<double>(size))},
                              {"position_before",N(static_cast<double>(before))},{"rewind_result",B(rewound)},
                              {"file",J{}}});
            if(!rewound || size==0) error("Typeface "+std::to_string(id)+": font stream empty or not rewindable");
            else {
                auto bytes=SkData::MakeFromStream(stream.get(),size);
                if(!bytes || bytes->size()!=size) error("Typeface "+std::to_string(id)+": incomplete actual font stream read");
                else {
                    const auto filename="font-"+std::to_string(id)+".bin";
                    if(save(filename,bytes->data(),bytes->size())) streamRecord.object["file"]=S(filename);
                }
            }
            streamRecord.object["position_after"]=N(static_cast<double>(stream->getPosition()));
            record.object["font_stream"]=std::move(streamRecord);
        }
        typefaces.push_back(std::move(record));
        return id;
    }
};

sk_sp<SkTypeface> deserializeTypeface(SkStream& stream, void* opaque) {
    auto& ctx=*static_cast<Context*>(opaque);
    const bool hasPosition=stream.hasPosition();
    const auto before=stream.getPosition();
    const auto* memory=stream.getMemoryBase();
    // A null last-resort manager is essential: no platform family lookup can replace this stream.
    auto result=SkTypeface::MakeDeserialize(&stream,nullptr);
    const auto after=stream.getPosition();
    const int call=static_cast<int>(ctx.deserializeCalls.size());
    ctx.callbackFaces.push_back(result.get());
    J record=O({{"call_id",N(call)},{"stream_has_position",B(hasPosition)},
                {"stream_position_before",hasPosition?N(static_cast<double>(before)):J{}},
                {"stream_position_after",hasPosition?N(static_cast<double>(after)):J{}},
                {"stream_memory_same_as_original_skp",memory?B(memory==ctx.input->data()):J{}},
                {"stream_memory_pointer",S(pointer(memory))},{"last_resort_font_manager",J{}},
                {"returned_typeface_pointer",result?S(pointer(result.get())):J{}},
                {"typeface_id",J{}},{"status",S(result && result->countGlyphs()>0?"decoded":"failed")}});
    if(!result) ctx.error("Typeface deserialize call "+std::to_string(call)+" failed; default empty replacement must not be consumed");
    else record.object["typeface_id"]=N(ctx.face(result));
    ctx.deserializeCalls.push_back(std::move(record));
    return result;
}
sk_sp<SkImage> deserializeImage(const void* bytes,size_t length,std::optional<SkAlphaType> alpha,void* opaque) {
    auto& ctx=*static_cast<Context*>(opaque);
    const auto id=ctx.images.size();
    const auto filename="image-"+std::to_string(id)+".encoded";
    const bool saved=ctx.save(filename,bytes,length);
    auto data=SkData::MakeWithCopy(bytes,length);
    auto image=SkImages::DeferredFromEncodedData(std::move(data),alpha);
    ctx.images.push_back(O({{"id",N(static_cast<double>(id))},{"byte_count",N(static_cast<double>(length))},
                            {"file",saved?S(filename):J{}},{"alpha_type",alpha?N(static_cast<int>(*alpha)):J{}},
                            {"deferred_image_created",B(static_cast<bool>(image))},
                            {"pixels_decoded",B(false)}}));
    if(!image) ctx.error("Actual encoded image "+std::to_string(id)+" is unsupported/invalid; no replacement image supplied");
    return image;
}

class ProbeCanvas final : public SkNoDrawCanvas {
public:
    ProbeCanvas(Context& context,const SkIRect& bounds):SkNoDrawCanvas(bounds),ctx(context) {}
protected:
    void onDrawTextBlob(const SkTextBlob* blob,SkScalar x,SkScalar y,const SkPaint& paint) override {
        J draw=O({{"sequence",N(static_cast<double>(++ctx.sequence))},{"blob_runtime_id",N(blob->uniqueID())},
                  {"draw_origin",ctx.point({x,y})},{"blob_recorded_bounds",ctx.rect(blob->bounds())},
                  {"context",drawContext()},{"paint_summary",paintSummary(paint)},
                  {"dom_node_id",J{}},{"final_png_attribution",J{}}});
        std::vector<J> runs;
        for(SkTextBlobRunIterator it(blob);!it.done();it.next()) {
            const auto& font=it.font();
            auto tf=font.refTypeface();
            const int fontId=ctx.face(tf);
            std::vector<J> callbackIDs;
            for(size_t i=0;i<ctx.callbackFaces.size();++i)
                if(tf && ctx.callbackFaces[i]==tf.get()) callbackIDs.push_back(N(static_cast<double>(i)));
            if(callbackIDs.empty()) ctx.error("Blob run typeface lacks actual same-object deserialize callback binding");
            const int mode=static_cast<int>(it.positioning());
            const unsigned scalars=it.scalarsPerGlyph();
            const unsigned expected=mode==0?0:mode==1?1:mode==2?2:mode==3?4:99;
            const char* names[]={"default-implicit-advances","horizontal-x","full-xy","rsxform"};
            J run=O({{"typeface_id",fontId>=0?N(fontId):J{}},{"same_object_deserialize_call_ids",A(std::move(callbackIDs))},
                     {"glyph_count",N(it.glyphCount())},{"positioning_enum",N(mode)},
                     {"positioning",mode>=0 && mode<=3?S(names[mode]):J{}},
                     {"scalars_per_glyph",N(scalars)},{"run_offset",ctx.point(it.offset())},
                     {"font",O({{"size",ctx.scalar(font.getSize(),"font.size")},
                                 {"scale_x",ctx.scalar(font.getScaleX(),"font.scale_x")},
                                 {"skew_x",ctx.scalar(font.getSkewX(),"font.skew_x")},
                                 {"embolden",B(font.isEmbolden())},{"subpixel",B(font.isSubpixel())},
                                 {"linear_metrics",B(font.isLinearMetrics())},
                                 {"edging_enum",N(static_cast<int>(font.getEdging()))},
                                 {"hinting_enum",N(static_cast<int>(font.getHinting()))}})},
                     {"source_text",J{}},{"source_clusters",J{}},{"source_utf8_byte_count",N(it.textSize())},
                     {"glyph_ink_bounds",J{}},{"visible_glyph_bounds",J{}}});
            std::vector<J> glyphs,positions;
            for(uint32_t i=0;i<it.glyphCount();++i) glyphs.push_back(N(it.glyphs()[i])); // ID 0 is retained.
            if(scalars!=expected) ctx.error("Unsupported/mismatched actual run positioning");
            else for(uint64_t i=0;i<static_cast<uint64_t>(it.glyphCount())*scalars;++i)
                positions.push_back(ctx.scalar(it.pos()[i],"run.position"));
            run.object["glyph_ids"]=A(std::move(glyphs));
            run.object["raw_position_scalars"]=A(std::move(positions));
            if(it.textSize()) {
                if(!it.text() || !it.clusters()) ctx.error("Extended blob run lacks actual text/cluster storage");
                else {
                    run.object["source_text"]=O({{"encoding",S("raw UTF-8 bytes, no reverse glyph mapping")},
                                                 {"hex",S(hex(it.text(),it.textSize()))}});
                    std::vector<J> clusters;
                    for(uint32_t i=0;i<it.glyphCount();++i) clusters.push_back(N(it.clusters()[i]));
                    run.object["source_clusters"]=A(std::move(clusters));
                }
            }
            runs.push_back(std::move(run));
        }
        draw.object["runs"]=A(std::move(runs));
        ctx.blobs.push_back(std::move(draw));
    }
    void onDrawPicture(const SkPicture* picture,const SkMatrix* matrix,const SkPaint* paint) override {
        ctx.nestedPictures.push_back(O({{"sequence",N(static_cast<double>(++ctx.sequence))},
            {"runtime_id",N(picture->uniqueID())},{"cull_rect",ctx.rect(picture->cullRect())},
            {"context_before",drawContext()},{"has_matrix",B(matrix!=nullptr)},
            {"has_paint",B(paint!=nullptr)}}));
        // SkNoDrawCanvas deliberately discards pictures. The base SkCanvas implementation
        // preserves real save/matrix/paint semantics while routing nested blobs to this observer.
        SkCanvas::onDrawPicture(picture,matrix,paint);
    }
    void onDrawAnnotation(const SkRect& rect,const char key[],SkData* data) override {
        ctx.annotations.push_back(O({{"sequence",N(static_cast<double>(++ctx.sequence))},
            {"rect",ctx.rect(rect)},{"key",key?S(key):J{}},{"context",drawContext()},
            {"data_byte_count",data?N(static_cast<double>(data->size())):J{}},
            {"data_hex",data?S(hex(data->data(),data->size())):J{}},
            {"interpreted_dom_node_id",J{}}}));
    }
    void onDrawDrawable(SkDrawable*,const SkMatrix*) override {
        ctx.error("Actual picture contains a drawable; this bounded observer has no drawable traversal proof");
    }
private:
    Context& ctx;
    J drawContext() {
        std::vector<J> matrix;
        const auto m=getLocalToDevice();
        for(int row=0;row<4;++row) for(int col=0;col<4;++col)
            matrix.push_back(ctx.scalar(m.rc(row,col),"ctm"));
        const auto clip=getDeviceClipBounds();
        return O({{"local_to_device_row_major",A(std::move(matrix))},
                  {"conservative_device_clip_bounds",A({N(clip.left()),N(clip.top()),N(clip.right()),N(clip.bottom())})},
                  {"clip_quantity",S("SkNoDrawCanvas conservative rectangular clip, not actual clip mask or final visibility")}});
    }
    J paintSummary(const SkPaint& paint) {
        const auto c=paint.getColor4f();
        return O({{"color4f",A({ctx.scalar(c.fR,"color.r"),ctx.scalar(c.fG,"color.g"),
                                ctx.scalar(c.fB,"color.b"),ctx.scalar(c.fA,"color.a")})},
                  {"antialias",B(paint.isAntiAlias())},{"style_enum",N(static_cast<int>(paint.getStyle()))},
                  {"stroke_width",ctx.scalar(paint.getStrokeWidth(),"paint.stroke_width")},
                  {"stroke_miter",ctx.scalar(paint.getStrokeMiter(),"paint.stroke_miter")},
                  {"stroke_cap_enum",N(static_cast<int>(paint.getStrokeCap()))},
                  {"stroke_join_enum",N(static_cast<int>(paint.getStrokeJoin()))},
                  {"has_shader",B(paint.getShader()!=nullptr)},{"has_color_filter",B(paint.getColorFilter()!=nullptr)},
                  {"has_mask_filter",B(paint.getMaskFilter()!=nullptr)},{"has_image_filter",B(paint.getImageFilter()!=nullptr)},
                  {"quantity",S("Raw public paint properties; not decoded shader/filter paint or sampled pixels")}});
    }
};
} // namespace

int main(int argc,char** argv) {
    const char* ci=std::getenv("GITHUB_ACTIONS");
    if(!ci || std::string(ci)!="true" || argc!=3) return 2;
    SkGraphics::Init();
    Context ctx;
    ctx.output=argv[2];
    ctx.input=SkData::MakeFromFileName(argv[1]);
    sk_sp<SkPicture> picture;
    bool playbackAttempted=false;
    if(!ctx.input) ctx.error("Cannot read selected original SKP");
    else {
        SkDeserialProcs procs;
        procs.fTypefaceStreamProc=deserializeTypeface;
        procs.fTypefaceCtx=&ctx;
        procs.fImageProc=deserializeImage;
        procs.fImageCtx=&ctx;
        picture=SkPicture::MakeFromData(ctx.input.get(),&procs);
        if(!picture) ctx.error("Pinned SkPicture parser rejected actual stream");
        else if(!picture->cullRect().isFinite()) ctx.error("Actual picture has a nonfinite cull rectangle");
        // SkPictureData may internally replace a failed typeface with MakeEmpty. Never
        // consume the replacement: callback failure remains fatal before any playback.
        if(picture && ctx.errors.empty()) {
            playbackAttempted=true;
            ProbeCanvas canvas(ctx,picture->cullRect().roundOut());
            picture->playback(&canvas);
        }
    }
    J cull=picture?ctx.rect(picture->cullRect()):J{};
    const bool ok=ctx.errors.empty() && picture && playbackAttempted;
    J output=O({{"schema",S("raw-skp-text-v1")},
        {"status",S(ok?"decoded":"failed")},{"canonical_output",B(false)},
        {"skia_revision",S("95ee33d7ec7791ab9c071675710a14fe6408ae4f")},
        {"input_file",S(argv[1])},{"input_byte_count",ctx.input?N(static_cast<double>(ctx.input->size())):J{}},
        {"picture_cull_rect",std::move(cull)},
        {"playback_attempted",B(playbackAttempted)},{"rasterized",B(false)},
        {"dom_source_attribution",J{}},{"final_png_attribution",J{}},
        {"limits",A({S("Trace source event/layer/frame ownership remains external and unproved"),
                     S("Blob source UTF-8 and clusters may be absent in ordinary glyph-only display items"),
                     S("No reverse Unicode mapping, reshaping, glyph ink bounds, or final visible glyph measurement"),
                     S("NoDrawCanvas uses conservative rectangular clipping; playback records do not certify PNG visibility")})},
        {"typeface_deserialize_calls",A(std::move(ctx.deserializeCalls))},
        {"typefaces",A(std::move(ctx.typefaces))},{"encoded_images",A(std::move(ctx.images))},
        {"draw_text_blobs",A(std::move(ctx.blobs))},{"annotations",A(std::move(ctx.annotations))},
        {"nested_pictures",A(std::move(ctx.nestedPictures))},{"errors",A(std::move(ctx.errors))}});
    std::ofstream result(ctx.output+"/raw.json",std::ios::binary);
    if(!result) return 1;
    json(result,output); result << '\n';
    return ok && result.good()?0:1;
}
